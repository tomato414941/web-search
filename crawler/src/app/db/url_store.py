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

    def __init__(self, db_path: str, recrawl_after_days: int = 30):
        self.db_path = db_path
        self.recrawl_threshold = recrawl_after_days * 86400
        self._init_db()

    def _init_db(self):
        # Schema is managed by Alembic; verify connectivity only.
        con = get_connection(self.db_path)
        con.close()

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

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            added = self._upsert_pending_url(
                cur,
                url_hash_value=h,
                url=url,
                domain=domain,
                priority=priority,
                now=now,
                cutoff=cutoff,
            )
            con.commit()
            cur.close()
            return added
        finally:
            con.close()

    def add_batch(
        self,
        urls: list[str],
        priority: float = 0.0,
    ) -> int:
        """
        Add multiple URLs as pending.

        Returns:
            Number of URLs added
        """
        if not urls:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)

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

            con.commit()
            cur.close()
            return added
        finally:
            con.close()

    def add_batch_scored(
        self,
        items: list[tuple[str, float]],
    ) -> int:
        """
        Add multiple (url, priority) pairs as pending in a single transaction.

        Returns:
            Number of URLs added
        """
        if not items:
            return 0

        added = 0
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url, priority in items:
                h = url_hash(url)
                domain = get_domain(url)
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
            con.commit()
            cur.close()
            return added
        finally:
            con.close()

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

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            rows = self._pop_pending_rows(
                cur,
                count=count,
                max_per_domain=max_per_domain,
            )

            con.commit()
            cur.close()

            return [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    created_at=row[4],
                )
                for row in rows
            ]
        finally:
            con.close()

    def requeue_for_retry(self, url: str, priority: float) -> bool:
        """Move a URL from crawling back to pending for retry.

        Only transitions crawling -> pending. Returns True if transitioned.
        """
        h = url_hash(url)
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                UPDATE urls
                SET status = 'pending', priority = {ph}
                WHERE url_hash = {ph} AND status = 'crawling'
                """,
                (priority, h),
            )
            affected = cur.rowcount
            con.commit()
            cur.close()
            return affected > 0
        finally:
            con.close()

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
        affected = 0
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                h = url_hash(url)
                cur.execute(
                    f"""
                    UPDATE urls
                    SET status = {ph}, last_crawled_at = {ph}
                    WHERE url_hash = {ph} AND status = 'crawling'
                    """,
                    (status, now, h),
                )
                affected += cur.rowcount
            con.commit()
            cur.close()
            return affected
        finally:
            con.close()

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

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
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
            con.commit()
            cur.close()
        finally:
            con.close()

    def pending_count(self) -> int:
        """Return number of pending URLs."""
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'pending'")
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()

    def contains(self, url: str) -> bool:
        """Check if URL exists in any status."""
        h = url_hash(url)
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(f"SELECT 1 FROM urls WHERE url_hash = {ph}", (h,))
            result = cur.fetchone() is not None
            cur.close()
            return result
        finally:
            con.close()

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

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT 1 FROM urls
                WHERE url_hash = {ph} AND last_crawled_at > {ph}
                """,
                (h, cutoff),
            )
            result = cur.fetchone() is not None
            cur.close()
            return result
        finally:
            con.close()

    def peek(self, count: int = 10) -> list[UrlItem]:
        """View top pending URLs without modifying them."""
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
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
            result = [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    created_at=row[4],
                )
                for row in cur.fetchall()
            ]
            cur.close()
            return result
        finally:
            con.close()

    def get_stale_urls(self, limit: int = 100) -> list[str]:
        """Get URLs ready for re-crawl (done and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT url FROM urls
                WHERE last_crawled_at < {ph} AND status = 'done'
                ORDER BY last_crawled_at ASC
                LIMIT {ph}
                """,
                (cutoff, limit),
            )
            result = [row[0] for row in cur.fetchall()]
            cur.close()
            return result
        finally:
            con.close()

    def get_stale_url_count(self) -> int:
        """Count URLs ready for re-crawl (done and past threshold)."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT COUNT(*) FROM urls
                WHERE last_crawled_at < {ph} AND status = 'done'
                """,
                (cutoff,),
            )
            count = cur.fetchone()[0]
            cur.close()
            return count
        finally:
            con.close()

    def recover_stale_crawling(self) -> int:
        """
        Reset stale 'crawling' URLs back to 'pending'.
        Called at startup to recover from crashes.

        Returns:
            Number of URLs recovered
        """
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("UPDATE urls SET status = 'pending' WHERE status = 'crawling'")
            count = cur.rowcount
            con.commit()
            cur.close()
            return count
        finally:
            con.close()

    def get_stats(self) -> dict:
        """Get URL statistics."""
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()

            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'pending'")
            pending = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'crawling'")
            crawling = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'done'")
            done = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'failed'")
            failed = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM urls WHERE last_crawled_at > {ph}", (cutoff,)
            )
            recent = cur.fetchone()[0]

            cur.close()

            return {
                "pending": pending,
                "crawling": crawling,
                "done": done,
                "failed": failed,
                "total": pending + crawling + done + failed,
                "recent": recent,
            }
        finally:
            con.close()

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """Get domain counts for done URLs."""
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
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
            result = [(row[0], row[1]) for row in cur.fetchall()]
            cur.close()
            return result
        finally:
            con.close()

    def get_pending_domains(self, limit: int = 15) -> list[tuple[str, int]]:
        """Get top domains by pending URL count."""
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
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
            result = [(row[0], row[1]) for row in cur.fetchall()]
            cur.close()
            return result
        finally:
            con.close()

    def domain_done_count(self, domain: str) -> int:
        """Return number of 'done' URLs for a given domain."""
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT COUNT(*) FROM urls WHERE domain = {ph} AND status = 'done'",
                (domain,),
            )
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()

    def domain_done_count_batch(self, domains: list[str]) -> dict[str, int]:
        """Return done-URL counts for multiple domains in a single query."""
        if not domains:
            return {}
        phs = sql_placeholders(len(domains))
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"SELECT domain, COUNT(*) FROM urls "
                f"WHERE domain IN ({phs}) AND status = 'done' "
                f"GROUP BY domain",
                tuple(domains),
            )
            result = {row[0]: row[1] for row in cur.fetchall()}
            cur.close()
            return result
        finally:
            con.close()

    def size(self) -> int:
        """Return total number of URLs (all statuses). For health checks."""
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM urls")
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()

    def mark_seeds(self, urls: list[str]) -> int:
        """Set is_seed = TRUE for the given URLs."""
        if not urls:
            return 0

        ph = sql_placeholder()
        marked = 0
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                h = url_hash(url)
                cur.execute(
                    f"UPDATE urls SET is_seed = TRUE WHERE url_hash = {ph}",
                    (h,),
                )
                marked += cur.rowcount
            con.commit()
            cur.close()
            return marked
        finally:
            con.close()

    def unmark_seeds(self, urls: list[str]) -> int:
        """Set is_seed = FALSE for the given URLs."""
        if not urls:
            return 0

        ph = sql_placeholder()
        unmarked = 0
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                h = url_hash(url)
                cur.execute(
                    f"UPDATE urls SET is_seed = FALSE WHERE url_hash = {ph}",
                    (h,),
                )
                unmarked += cur.rowcount
            con.commit()
            cur.close()
            return unmarked
        finally:
            con.close()

    def purge_blocked_domains(self, blocklist: frozenset[str]) -> int:
        """Delete pending URLs whose domain matches the blocklist.

        Uses subdomain matching: blocking 'facebook.com' also removes
        'www.facebook.com', 'm.facebook.com', etc.

        Returns the number of deleted rows.
        """
        if not blocklist:
            return 0

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            # Build WHERE conditions for each blocked domain
            conditions = []
            params: list[str] = []
            for d in blocklist:
                conditions.append(f"domain = {sql_placeholder()}")
                params.append(d)
                conditions.append(f"domain LIKE {sql_placeholder()}")
                params.append(f"%.{d}")

            where = " OR ".join(conditions)
            cur.execute(
                f"DELETE FROM urls WHERE status = 'pending' AND ({where})",
                params,
            )
            deleted = cur.rowcount
            con.commit()
            cur.close()
            return deleted
        finally:
            con.close()

    def get_seeds(self) -> list[dict]:
        """Get all URLs marked as seeds."""
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT url, domain, status, priority, created_at, last_crawled_at"
                " FROM urls WHERE is_seed = TRUE ORDER BY created_at DESC"
            )
            result = [
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
            cur.close()
            return result
        finally:
            con.close()
