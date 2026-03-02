"""
URL Store - Unified URL Management

Manages the full URL lifecycle: pending → crawling → done/failed.
Replaces the separate Frontier and History tables.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.db.connection import db_connection, db_transaction
from shared.postgres.search import (
    get_connection,
    sql_placeholder,
    sql_placeholders,
)


def url_hash(url: str) -> str:
    """Generate 16-character hash for URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def get_domain(url: str) -> str:
    """Extract domain hostname from URL (lowercase, no port)."""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


@dataclass
class UrlItem:
    url: str
    domain: str
    priority: float
    created_at: int


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority REAL NOT NULL DEFAULT 0,
    crawl_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_crawled_at INTEGER,
    is_seed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_urls_pending ON urls(priority DESC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);
CREATE INDEX IF NOT EXISTS idx_urls_recrawl ON urls(last_crawled_at) WHERE status IN ('done', 'failed');
"""


class UrlStore:
    """
    Unified URL storage.

    Manages the full lifecycle of URLs:
    - pending: discovered, waiting to be crawled
    - crawling: currently being fetched
    - done: successfully crawled
    - failed: crawl failed
    """

    def __init__(
        self,
        db_path: str,
        recrawl_after_days: int = 30,
        max_pending_per_domain: int = 0,
    ):
        self.db_path = db_path
        self.recrawl_threshold = recrawl_after_days * 86400
        self.max_pending_per_domain = max_pending_per_domain
        self._init_db()

    def _init_db(self):
        # Schema is managed by Alembic; verify connectivity only.
        con = get_connection(self.db_path)
        con.close()

    def _get_pending_counts_batch(self, cur: Any, domains: list[str]) -> dict[str, int]:
        """Get pending URL counts per domain in a single query."""
        if not domains:
            return {}
        ph = sql_placeholder()
        cur.execute(
            f"SELECT domain, COUNT(*) FROM urls "
            f"WHERE domain = ANY({ph}) AND status = 'pending' "
            f"GROUP BY domain",
            (domains,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    def _upsert_pending_url(
        self,
        cur: Any,
        *,
        url_hash_value: str,
        url: str,
        domain: str,
        priority: float,
        now: int,
        cutoff: int,
    ) -> bool:
        ph = sql_placeholder()
        cur.execute(
            f"""
            INSERT INTO urls (url_hash, url, domain, status, priority, crawl_count, created_at)
            VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, 0, {ph})
            ON CONFLICT (url_hash) DO UPDATE SET
                status = 'pending',
                priority = EXCLUDED.priority
            WHERE urls.status IN ('done', 'failed') AND urls.last_crawled_at < {ph}
            """,
            (url_hash_value, url, domain, priority, now, cutoff),
        )
        return cur.rowcount > 0

    def _pop_pending_rows(
        self,
        cur: Any,
        *,
        count: int,
        max_per_domain: int,
    ) -> list[tuple[Any, ...]]:
        ph = sql_placeholder()

        # Overscan to ensure enough domain diversity after per-domain cap
        overscan = count * max_per_domain * 3
        cur.execute(
            f"""
            WITH top_candidates AS (
                SELECT url_hash, url, domain, priority, created_at,
                       priority + LEAST(20.0,
                           (EXTRACT(EPOCH FROM NOW())::BIGINT - created_at)
                           / 86400.0 * 0.5
                       ) AS eff_pri
                FROM urls
                WHERE status = 'pending'
                ORDER BY priority DESC
                LIMIT {ph}
                FOR UPDATE SKIP LOCKED
            ),
            per_domain AS (
                SELECT url_hash, url, domain, priority, created_at, eff_pri,
                       ROW_NUMBER() OVER (
                           PARTITION BY domain ORDER BY eff_pri DESC
                       ) AS rn
                FROM top_candidates
            ),
            selected AS (
                SELECT url_hash
                FROM per_domain
                WHERE rn <= {ph}
                ORDER BY eff_pri DESC
                LIMIT {ph}
            )
            UPDATE urls
            SET status = 'crawling'
            FROM selected s
            WHERE urls.url_hash = s.url_hash
            RETURNING urls.url_hash, urls.url, urls.domain,
                      urls.priority, urls.created_at
            """,
            (overscan, max_per_domain, count),
        )
        return cur.fetchall()

    def add(
        self,
        url: str,
        priority: float = 0.0,
    ) -> bool:
        """
        Add a URL as pending. Skips if already pending/crawling.
        Re-adds if done/failed and past recrawl threshold.

        Returns:
            True if added/re-queued, False otherwise
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        with db_transaction(self.db_path) as cur:
            return self._upsert_pending_url(
                cur,
                url_hash_value=h,
                url=url,
                domain=domain,
                priority=priority,
                now=now,
                cutoff=cutoff,
            )

    def add_batch(
        self,
        urls: list[str],
        priority: float = 0.0,
    ) -> int:
        """
        Add multiple URLs as pending.
        Respects per-domain pending cap (max_pending_per_domain).

        Returns:
            Number of URLs added
        """
        if not urls:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        cap = self.max_pending_per_domain

        with db_transaction(self.db_path) as cur:
            pending: dict[str, int] = {}
            if cap > 0:
                domains = list({get_domain(u) for u in urls})
                pending = self._get_pending_counts_batch(cur, domains)
            batch_adds: dict[str, int] = {}

            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)
                if cap > 0:
                    current = pending.get(domain, 0) + batch_adds.get(domain, 0)
                    if current >= cap:
                        continue
                if self._upsert_pending_url(
                    cur,
                    url_hash_value=h,
                    url=url,
                    domain=domain,
                    priority=priority,
                    now=now,
                    cutoff=cutoff,
                ):
                    added += 1
                    if cap > 0:
                        batch_adds[domain] = batch_adds.get(domain, 0) + 1

            return added

    def add_batch_scored(
        self,
        items: list[tuple[str, float]],
    ) -> int:
        """
        Add multiple (url, priority) pairs as pending in a single transaction.
        Respects per-domain pending cap (max_pending_per_domain).

        Returns:
            Number of URLs added
        """
        if not items:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        cap = self.max_pending_per_domain

        with db_transaction(self.db_path) as cur:
            pending: dict[str, int] = {}
            if cap > 0:
                domains = list({get_domain(url) for url, _ in items})
                pending = self._get_pending_counts_batch(cur, domains)
            batch_adds: dict[str, int] = {}

            for url, priority in items:
                h = url_hash(url)
                domain = get_domain(url)
                if cap > 0:
                    current = pending.get(domain, 0) + batch_adds.get(domain, 0)
                    if current >= cap:
                        continue
                if self._upsert_pending_url(
                    cur,
                    url_hash_value=h,
                    url=url,
                    domain=domain,
                    priority=priority,
                    now=now,
                    cutoff=cutoff,
                ):
                    added += 1
                    if cap > 0:
                        batch_adds[domain] = batch_adds.get(domain, 0) + 1
            return added

    def pop_batch(self, count: int, max_per_domain: int = 3) -> list[UrlItem]:
        """
        Get pending URLs and mark them as crawling.
        Ensures domain diversity by limiting URLs per domain.

        Args:
            count: Maximum number of URLs to return
            max_per_domain: Maximum URLs from a single domain

        Returns:
            List of UrlItems
        """
        if count <= 0:
            return []

        with db_transaction(self.db_path) as cur:
            rows = self._pop_pending_rows(
                cur,
                count=count,
                max_per_domain=max_per_domain,
            )

            return [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    created_at=row[4],
                )
                for row in rows
            ]

    def requeue_for_retry(self, url: str, priority: float) -> bool:
        """Move a URL from crawling back to pending for retry.

        Only transitions crawling -> pending. Returns True if transitioned.
        """
        h = url_hash(url)
        ph = sql_placeholder()
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                UPDATE urls
                SET status = 'pending', priority = {ph}
                WHERE url_hash = {ph} AND status = 'crawling'
                """,
                (priority, h),
            )
            return cur.rowcount > 0

    def release_urls(self, urls: list[str], status: str = "failed") -> int:
        """Release URLs from crawling to another status.

        Used to release blocked URLs that were popped from the queue
        but filtered out by the scheduler. Only transitions crawling -> target status.
        Returns count of affected rows.
        """
        if not urls:
            return 0
        ph = sql_placeholder()
        now = int(time.time())
        hashes = [url_hash(u) for u in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                UPDATE urls
                SET status = {ph}, last_crawled_at = {ph}
                WHERE url_hash = ANY({ph}) AND status = 'crawling'
                """,
                (status, now, hashes),
            )
            return cur.rowcount

    def record(self, url: str, status: str = "done") -> None:
        """
        Record a crawl result. Updates status, last_crawled_at, crawl_count.

        Args:
            url: Crawled URL
            status: 'done' or 'failed'
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())
        ph = sql_placeholder()

        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                INSERT INTO urls (url_hash, url, domain, status, priority, crawl_count, created_at, last_crawled_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, 0, 1, {ph}, {ph})
                ON CONFLICT (url_hash) DO UPDATE SET
                    status = EXCLUDED.status,
                    last_crawled_at = EXCLUDED.last_crawled_at,
                    crawl_count = urls.crawl_count + 1
                """,
                (h, url, domain, status, now, now),
            )

    def pending_count(self) -> int:
        """Return number of pending URLs."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'pending'")
            return cur.fetchone()[0]

    def contains(self, url: str) -> bool:
        """Check if URL exists in any status."""
        h = url_hash(url)
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(f"SELECT 1 FROM urls WHERE url_hash = {ph}", (h,))
            return cur.fetchone() is not None

    def is_recently_crawled(self, url: str) -> bool:
        """
        Check if URL was crawled within recrawl threshold.

        Returns:
            True if recently crawled (should skip)
        """
        h = url_hash(url)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT 1 FROM urls
                WHERE url_hash = {ph} AND last_crawled_at > {ph}
                """,
                (h, cutoff),
            )
            return cur.fetchone() is not None

    def peek(self, count: int = 10) -> list[UrlItem]:
        """View top pending URLs without modifying them."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url_hash, url, domain, priority, created_at
                FROM urls
                WHERE status = 'pending'
                ORDER BY priority DESC
                LIMIT {ph}
                """,
                (count,),
            )
            return [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    created_at=row[4],
                )
                for row in cur.fetchall()
            ]

    def get_stale_urls(self, limit: int = 100) -> list[str]:
        """Get URLs ready for re-crawl (done and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT url FROM urls
                WHERE last_crawled_at < {ph} AND status = 'done'
                ORDER BY last_crawled_at ASC
                LIMIT {ph}
                """,
                (cutoff, limit),
            )
            return [row[0] for row in cur.fetchall()]

    def get_stale_url_count(self) -> int:
        """Count URLs ready for re-crawl (done and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM urls
                WHERE last_crawled_at < {ph} AND status = 'done'
                """,
                (cutoff,),
            )
            return cur.fetchone()[0]

    def recover_stale_crawling(self) -> int:
        """
        Reset stale 'crawling' URLs back to 'pending'.
        Called at startup to recover from crashes.

        Returns:
            Number of URLs recovered
        """
        with db_transaction(self.db_path) as cur:
            cur.execute("UPDATE urls SET status = 'pending' WHERE status = 'crawling'")
            return cur.rowcount

    def get_stats(self) -> dict:
        """Get URL statistics.

        Uses pg_class/pg_stats for approximate per-status counts when
        available (large tables), falling back to exact COUNT for small
        or freshly-created tables where pg_stats has no data yet.
        """
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        with db_connection(self.db_path) as cur:
            # Try approximate counts from pg_class + pg_stats
            cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'urls'")
            row = cur.fetchone()
            total = row[0] if row and row[0] > 0 else 0

            status_counts: dict[str, int] | None = None
            if total > 0:
                cur.execute(
                    "SELECT unnest(most_common_vals::text::text[]) AS status,"
                    " unnest(most_common_freqs) AS freq"
                    " FROM pg_stats"
                    " WHERE tablename = 'urls' AND attname = 'status'"
                )
                rows = cur.fetchall()
                if rows:
                    status_counts = {r[0]: round(total * r[1]) for r in rows}

            if status_counts is not None:
                # Fast path: approximate counts + indexed recent query
                cur.execute(
                    f"SELECT COUNT(*) FROM urls WHERE last_crawled_at > {ph}",
                    (cutoff,),
                )
                recent = cur.fetchone()[0]
                return {
                    "pending": status_counts.get("pending", 0),
                    "crawling": status_counts.get("crawling", 0),
                    "done": status_counts.get("done", 0),
                    "failed": status_counts.get("failed", 0),
                    "total": total,
                    "recent": recent,
                }

            # Fallback: exact counts (small tables / no pg_stats data)
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'crawling') AS crawling,
                    COUNT(*) FILTER (WHERE status = 'done') AS done,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE last_crawled_at > {ph}) AS recent
                FROM urls
                """,
                (cutoff,),
            )
            row = cur.fetchone()
            return {
                "pending": row[0],
                "crawling": row[1],
                "done": row[2],
                "failed": row[3],
                "total": row[4],
                "recent": row[5],
            }

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """Get domain counts for done URLs."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM urls
                WHERE status = 'done'
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT {ph}
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def get_pending_domains(self, limit: int = 15) -> list[tuple[str, int]]:
        """Get top domains by pending URL count."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM urls
                WHERE status = 'pending'
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT {ph}
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    def domain_done_count(self, domain: str) -> int:
        """Return number of 'done' URLs for a given domain."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM urls WHERE domain = {ph} AND status = 'done'",
                (domain,),
            )
            return cur.fetchone()[0]

    def domain_done_count_batch(self, domains: list[str]) -> dict[str, int]:
        """Return done-URL counts for multiple domains in a single query."""
        if not domains:
            return {}
        phs = sql_placeholders(len(domains))
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"SELECT domain, COUNT(*) FROM urls "
                f"WHERE domain IN ({phs}) AND status = 'done' "
                f"GROUP BY domain",
                tuple(domains),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def size(self) -> int:
        """Return total number of URLs (all statuses). For health checks."""
        with db_connection(self.db_path) as cur:
            cur.execute("SELECT COUNT(*) FROM urls")
            return cur.fetchone()[0]

    def mark_seeds(self, urls: list[str]) -> int:
        """Set is_seed = TRUE for the given URLs."""
        if not urls:
            return 0

        ph = sql_placeholder()
        hashes = [url_hash(u) for u in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"UPDATE urls SET is_seed = TRUE WHERE url_hash = ANY({ph})",
                (hashes,),
            )
            return cur.rowcount

    def unmark_seeds(self, urls: list[str]) -> int:
        """Set is_seed = FALSE for the given URLs."""
        if not urls:
            return 0

        ph = sql_placeholder()
        hashes = [url_hash(u) for u in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"UPDATE urls SET is_seed = FALSE WHERE url_hash = ANY({ph})",
                (hashes,),
            )
            return cur.rowcount

    def purge_blocked_domains(self, blocklist: frozenset[str]) -> int:
        """Delete pending URLs whose domain matches the blocklist.

        Uses subdomain matching: blocking 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted rows.
        """
        if not blocklist:
            return 0

        with db_transaction(self.db_path) as cur:
            # Build WHERE conditions for each blocked domain
            conditions = []
            params: list[str] = []
            for d in blocklist:
                conditions.append(f"domain = {sql_placeholder()}")
                params.append(d)
                # Escape SQL LIKE wildcards in domain name
                escaped = (
                    d.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                conditions.append(f"domain LIKE {sql_placeholder()} ESCAPE '\\'")
                params.append(f"%.{escaped}")

            where = " OR ".join(conditions)
            cur.execute(
                f"DELETE FROM urls WHERE status = 'pending' AND ({where})",
                params,
            )
            return cur.rowcount

    def get_seeds(self) -> list[dict]:
        """Get all URLs marked as seeds."""
        with db_connection(self.db_path) as cur:
            cur.execute(
                "SELECT url, domain, status, priority, created_at, last_crawled_at"
                " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
            )
            return [
                {
                    "url": row[0],
                    "domain": row[1],
                    "status": row[2],
                    "priority": row[3],
                    "created_at": row[4],
                    "last_crawled_at": row[5],
                }
                for row in cur.fetchall()
            ]
