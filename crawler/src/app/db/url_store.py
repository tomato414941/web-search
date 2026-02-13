"""
URL Store - Unified URL Management

Manages the full URL lifecycle: pending → crawling → done/failed.
Replaces the separate Frontier and History tables.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shared.db.search import (
    get_connection,
    is_postgres_mode,
    sql_placeholder,
    sql_placeholders,
)


def url_hash(url: str) -> str:
    """Generate 16-character hash for URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


@dataclass
class UrlItem:
    url: str
    domain: str
    priority: float
    created_at: int


SCHEMA_PG = """
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

SCHEMA_SQLITE = """
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
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);
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
        postgres_mode = is_postgres_mode()

        if not postgres_mode:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        con = get_connection(self.db_path)
        try:
            if postgres_mode:
                cur = con.cursor()
                for stmt in SCHEMA_PG.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cur.execute(stmt)
                # Migration: add is_seed column to existing tables
                cur.execute(
                    "ALTER TABLE urls ADD COLUMN IF NOT EXISTS"
                    " is_seed BOOLEAN NOT NULL DEFAULT FALSE"
                )
                # Migrate seeds table data if it exists
                cur.execute(
                    "SELECT EXISTS ("
                    "SELECT FROM information_schema.tables"
                    " WHERE table_name = 'seeds')"
                )
                if cur.fetchone()[0]:
                    cur.execute(
                        "UPDATE urls SET is_seed = TRUE"
                        " WHERE url IN (SELECT url FROM seeds)"
                    )
                # Create seed index after column exists
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_urls_seed"
                    " ON urls(url_hash) WHERE is_seed = TRUE"
                )
                con.commit()
                cur.close()
            else:
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SCHEMA_SQLITE)
                # Migration: add is_seed column if missing (SQLite)
                cur = con.cursor()
                cur.execute("PRAGMA table_info(urls)")
                columns = [row[1] for row in cur.fetchall()]
                if "is_seed" not in columns:
                    cur.execute(
                        "ALTER TABLE urls ADD COLUMN"
                        " is_seed BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                    # Migrate seeds table data if it exists
                    cur.execute(
                        "SELECT name FROM sqlite_master"
                        " WHERE type='table' AND name='seeds'"
                    )
                    if cur.fetchone():
                        cur.execute(
                            "UPDATE urls SET is_seed = TRUE"
                            " WHERE url IN (SELECT url FROM seeds)"
                        )
                    con.commit()
                cur.close()
        finally:
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
        postgres_mode: bool,
    ) -> bool:
        ph = sql_placeholder()
        if postgres_mode:
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

        cur.execute(
            f"SELECT status, last_crawled_at FROM urls WHERE url_hash = {ph}",
            (url_hash_value,),
        )
        existing = cur.fetchone()

        if existing is None:
            cur.execute(
                f"""
                INSERT INTO urls (url_hash, url, domain, status, priority, crawl_count, created_at)
                VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, 0, {ph})
                """,
                (url_hash_value, url, domain, priority, now),
            )
            return cur.rowcount > 0

        if existing[0] in ("done", "failed") and (existing[1] or 0) < cutoff:
            cur.execute(
                f"""
                UPDATE urls SET status = 'pending', priority = {ph}
                WHERE url_hash = {ph}
                """,
                (priority, url_hash_value),
            )
            return cur.rowcount > 0

        return False

    def _pop_pending_rows(
        self,
        cur: Any,
        *,
        count: int,
        max_per_domain: int,
        postgres_mode: bool,
    ) -> list[tuple[Any, ...]]:
        ph = sql_placeholder()
        ranked_query = """
            SELECT url_hash, url, domain, priority, created_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY domain ORDER BY priority DESC
                   ) AS rn
            FROM urls WHERE status = 'pending'
        """

        if postgres_mode:
            cur.execute(
                f"""
                WITH ranked AS (
                    {ranked_query}
                ),
                selected AS (
                    SELECT url_hash
                    FROM ranked
                    WHERE rn <= {ph}
                    ORDER BY rn ASC, priority DESC
                    LIMIT {ph}
                )
                UPDATE urls
                SET status = 'crawling'
                WHERE url_hash IN (SELECT url_hash FROM selected)
                RETURNING url_hash, url, domain, priority, created_at
                """,
                (max_per_domain, count),
            )
            return cur.fetchall()

        cur.execute(
            f"""
            SELECT url_hash, url, domain, priority, created_at
            FROM ({ranked_query}) ranked
            WHERE rn <= {ph}
            ORDER BY priority DESC
            LIMIT {ph}
            """,
            (max_per_domain, count),
        )
        rows = cur.fetchall()
        if not rows:
            return []

        hashes = [row[0] for row in rows]
        hash_placeholders = sql_placeholders(len(hashes))
        cur.execute(
            f"UPDATE urls SET status = 'crawling' WHERE url_hash IN ({hash_placeholders})",
            tuple(hashes),
        )
        return rows

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
        postgres_mode = is_postgres_mode()

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
                postgres_mode=postgres_mode,
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
        postgres_mode = is_postgres_mode()

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
                    postgres_mode=postgres_mode,
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

        postgres_mode = is_postgres_mode()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            rows = self._pop_pending_rows(
                cur,
                count=count,
                max_per_domain=max_per_domain,
                postgres_mode=postgres_mode,
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
            if is_postgres_mode():
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
            else:
                cur.execute(
                    f"SELECT 1 FROM urls WHERE url_hash = {ph}",
                    (h,),
                )
                if cur.fetchone():
                    cur.execute(
                        f"""
                        UPDATE urls SET status = {ph}, last_crawled_at = {ph}, crawl_count = crawl_count + 1
                        WHERE url_hash = {ph}
                        """,
                        (status, now, h),
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO urls (url_hash, url, domain, status, priority, crawl_count, created_at, last_crawled_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, 0, 1, {ph}, {ph})
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
