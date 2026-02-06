"""
URL Store - Unified URL Management

Manages the full URL lifecycle: pending → crawling → done/failed.
Replaces the separate Frontier and History tables.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from shared.db.search import get_connection, is_postgres_mode


def url_hash(url: str) -> str:
    """Generate 16-character hash for URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


@dataclass
class UrlItem:
    url: str
    domain: str
    priority: float
    source_url: Optional[str]
    created_at: int


SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS urls (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority REAL NOT NULL DEFAULT 0,
    source_url TEXT,
    crawl_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_crawled_at INTEGER
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
    source_url TEXT,
    crawl_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_crawled_at INTEGER
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
                con.commit()
                cur.close()
            else:
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SCHEMA_SQLITE)
        finally:
            con.close()

    def add(
        self,
        url: str,
        priority: float = 0.0,
        source_url: Optional[str] = None,
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
        ph = _placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO urls (url_hash, url, domain, status, priority, source_url, crawl_count, created_at)
                    VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, {ph}, 0, {ph})
                    ON CONFLICT (url_hash) DO UPDATE SET
                        status = 'pending',
                        priority = EXCLUDED.priority,
                        source_url = EXCLUDED.source_url
                    WHERE urls.status IN ('done', 'failed') AND urls.last_crawled_at < {ph}
                    """,
                    (h, url, domain, priority, source_url, now, cutoff),
                )
            else:
                # SQLite: check existence first, then insert or update
                cur.execute(
                    f"SELECT status, last_crawled_at FROM urls WHERE url_hash = {ph}",
                    (h,),
                )
                existing = cur.fetchone()

                if existing is None:
                    # New URL
                    cur.execute(
                        f"""
                        INSERT INTO urls (url_hash, url, domain, status, priority, source_url, crawl_count, created_at)
                        VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, {ph}, 0, {ph})
                        """,
                        (h, url, domain, priority, source_url, now),
                    )
                elif existing[0] in ("done", "failed") and (existing[1] or 0) < cutoff:
                    # Stale, re-queue
                    cur.execute(
                        f"""
                        UPDATE urls SET status = 'pending', priority = {ph}, source_url = {ph}
                        WHERE url_hash = {ph}
                        """,
                        (priority, source_url, h),
                    )
                else:
                    # Already pending/crawling or recently crawled
                    con.commit()
                    cur.close()
                    return False

            rowcount = cur.rowcount
            con.commit()
            cur.close()
            return rowcount > 0
        finally:
            con.close()

    def add_batch(
        self,
        urls: list[str],
        priority: float = 0.0,
        source_url: Optional[str] = None,
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
        ph = _placeholder()
        postgres_mode = is_postgres_mode()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)

                if postgres_mode:
                    cur.execute(
                        f"""
                        INSERT INTO urls (url_hash, url, domain, status, priority, source_url, crawl_count, created_at)
                        VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, {ph}, 0, {ph})
                        ON CONFLICT (url_hash) DO UPDATE SET
                            status = 'pending',
                            priority = EXCLUDED.priority,
                            source_url = EXCLUDED.source_url
                        WHERE urls.status IN ('done', 'failed') AND urls.last_crawled_at < {ph}
                        """,
                        (h, url, domain, priority, source_url, now, cutoff),
                    )
                else:
                    cur.execute(
                        f"SELECT status, last_crawled_at FROM urls WHERE url_hash = {ph}",
                        (h,),
                    )
                    existing = cur.fetchone()

                    if existing is None:
                        cur.execute(
                            f"""
                            INSERT INTO urls (url_hash, url, domain, status, priority, source_url, crawl_count, created_at)
                            VALUES ({ph}, {ph}, {ph}, 'pending', {ph}, {ph}, 0, {ph})
                            """,
                            (h, url, domain, priority, source_url, now),
                        )
                    elif (
                        existing[0] in ("done", "failed")
                        and (existing[1] or 0) < cutoff
                    ):
                        cur.execute(
                            f"""
                            UPDATE urls SET status = 'pending', priority = {ph}, source_url = {ph}
                            WHERE url_hash = {ph}
                            """,
                            (priority, source_url, h),
                        )
                    else:
                        continue

                if cur.rowcount > 0:
                    added += 1

            con.commit()
            cur.close()
            return added
        finally:
            con.close()

    def pop_batch(self, count: int) -> list[UrlItem]:
        """
        Get pending URLs and mark them as crawling.

        Args:
            count: Maximum number of URLs to return

        Returns:
            List of UrlItems
        """
        if count <= 0:
            return []

        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()

            if is_postgres_mode():
                cur.execute(
                    f"""
                    UPDATE urls SET status = 'crawling'
                    WHERE url_hash IN (
                        SELECT url_hash FROM urls
                        WHERE status = 'pending'
                        ORDER BY priority DESC
                        LIMIT {ph}
                    )
                    RETURNING url_hash, url, domain, priority, source_url, created_at
                    """,
                    (count,),
                )
                rows = cur.fetchall()
            else:
                # SQLite: SELECT then UPDATE
                cur.execute(
                    f"""
                    SELECT url_hash, url, domain, priority, source_url, created_at
                    FROM urls
                    WHERE status = 'pending'
                    ORDER BY priority DESC
                    LIMIT {ph}
                    """,
                    (count,),
                )
                rows = cur.fetchall()

                if rows:
                    hashes = [row[0] for row in rows]
                    placeholders = ",".join(ph for _ in hashes)
                    cur.execute(
                        f"UPDATE urls SET status = 'crawling' WHERE url_hash IN ({placeholders})",
                        tuple(hashes),
                    )

            con.commit()
            cur.close()

            return [
                UrlItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    source_url=row[4],
                    created_at=row[5],
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
        ph = _placeholder()

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
        ph = _placeholder()
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
        ph = _placeholder()

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
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT url_hash, url, domain, priority, source_url, created_at
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
                    source_url=row[4],
                    created_at=row[5],
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
        ph = _placeholder()

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
        ph = _placeholder()

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
        ph = _placeholder()
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
