"""
History - Visited URL Storage

Manages URLs that have been crawled.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.db.search import get_connection

from app.db.frontier import url_hash, get_domain


@dataclass
class HistoryItem:
    url: str
    domain: str
    status: str  # 'done' / 'failed'
    first_crawled_at: int
    last_crawled_at: int
    crawl_count: int


SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL,
    first_crawled_at INTEGER NOT NULL,
    last_crawled_at INTEGER NOT NULL,
    crawl_count INTEGER DEFAULT 1
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_history_domain ON history(domain);
CREATE INDEX IF NOT EXISTS idx_history_recrawl ON history(last_crawled_at);
CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
"""


class History:
    """
    Visited URL storage.

    Stores URLs that have been crawled, with status and timestamps.
    Used for:
    - Deduplication (is_recently_crawled)
    - Re-crawl scheduling (get_stale_urls)
    - Statistics
    """

    def __init__(self, db_path: str, recrawl_after_days: int = 30):
        self.db_path = db_path
        self.recrawl_threshold = recrawl_after_days * 86400
        self._init_db()

    def _init_db(self):
        """Initialize database."""
        turso_mode = os.getenv("TURSO_URL") is not None

        if not turso_mode:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        con = get_connection(self.db_path)
        try:
            if not turso_mode:
                con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
        finally:
            con.close()

    def record(
        self,
        url: str,
        status: str = "done",
    ) -> None:
        """
        Record a crawled URL.

        Args:
            url: Crawled URL
            status: 'done' or 'failed'
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())

        con = get_connection(self.db_path)
        try:
            con.execute(
                """
                INSERT INTO history (url_hash, url, domain, status, first_crawled_at, last_crawled_at, crawl_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(url_hash) DO UPDATE SET
                    status = excluded.status,
                    last_crawled_at = excluded.last_crawled_at,
                    crawl_count = crawl_count + 1
                """,
                (h, url, domain, status, now, now),
            )
            con.commit()
        finally:
            con.close()

    def record_batch(self, urls: list[str], status: str = "done") -> int:
        """
        Record multiple crawled URLs.

        Args:
            urls: Crawled URLs
            status: 'done' or 'failed'

        Returns:
            Number of URLs recorded
        """
        if not urls:
            return 0

        now = int(time.time())
        count = 0

        con = get_connection(self.db_path)
        try:
            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)

                con.execute(
                    """
                    INSERT INTO history (url_hash, url, domain, status, first_crawled_at, last_crawled_at, crawl_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(url_hash) DO UPDATE SET
                        status = excluded.status,
                        last_crawled_at = excluded.last_crawled_at,
                        crawl_count = crawl_count + 1
                    """,
                    (h, url, domain, status, now, now),
                )
                count += 1

            con.commit()
            return count
        finally:
            con.close()

    def is_recently_crawled(self, url: str) -> bool:
        """
        Check if URL was crawled within recrawl threshold.

        Returns:
            True if recently crawled (should skip)
            False if new or stale (can crawl)
        """
        h = url_hash(url)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        con = get_connection(self.db_path)
        try:
            cur = con.execute(
                "SELECT 1 FROM history WHERE url_hash = ? AND last_crawled_at > ?",
                (h, cutoff),
            )
            return cur.fetchone() is not None
        finally:
            con.close()

    def filter_new(self, urls: list[str]) -> list[str]:
        """
        Filter URLs to return only those not recently crawled.

        Args:
            urls: URLs to check

        Returns:
            URLs that are new or stale (can be crawled)
        """
        if not urls:
            return []

        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        result = []

        con = get_connection(self.db_path)
        try:
            for url in urls:
                h = url_hash(url)
                cur = con.execute(
                    "SELECT 1 FROM history WHERE url_hash = ? AND last_crawled_at > ?",
                    (h, cutoff),
                )
                if cur.fetchone() is None:
                    result.append(url)
            return result
        finally:
            con.close()

    def get_stale_urls(self, limit: int = 100) -> list[str]:
        """
        Get URLs that are ready for re-crawl.

        Returns:
            URLs where last_crawled_at < (now - recrawl_threshold)
        """
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        con = get_connection(self.db_path)
        try:
            cur = con.execute(
                """
                SELECT url FROM history
                WHERE last_crawled_at < ? AND status = 'done'
                ORDER BY last_crawled_at ASC
                LIMIT ?
                """,
                (cutoff, limit),
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            con.close()

    def get(self, url: str) -> Optional[HistoryItem]:
        """
        Get history for a specific URL.

        Returns:
            HistoryItem or None
        """
        h = url_hash(url)

        con = get_connection(self.db_path)
        try:
            cur = con.execute(
                """
                SELECT url, domain, status, first_crawled_at, last_crawled_at, crawl_count
                FROM history WHERE url_hash = ?
                """,
                (h,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return HistoryItem(
                url=row[0],
                domain=row[1],
                status=row[2],
                first_crawled_at=row[3],
                last_crawled_at=row[4],
                crawl_count=row[5],
            )
        finally:
            con.close()

    def count(self, status: Optional[str] = None) -> int:
        """
        Count URLs in history.

        Args:
            status: Optional filter by status ('done', 'failed')

        Returns:
            Count of URLs
        """
        con = get_connection(self.db_path)
        try:
            if status:
                cur = con.execute(
                    "SELECT COUNT(*) FROM history WHERE status = ?", (status,)
                )
            else:
                cur = con.execute("SELECT COUNT(*) FROM history")
            return cur.fetchone()[0]
        finally:
            con.close()

    def get_stats(self) -> dict:
        """
        Get history statistics.

        Returns:
            Dict with total, done, failed, recent counts
        """
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        con = get_connection(self.db_path)
        try:
            total = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            done = con.execute(
                "SELECT COUNT(*) FROM history WHERE status = 'done'"
            ).fetchone()[0]
            failed = con.execute(
                "SELECT COUNT(*) FROM history WHERE status = 'failed'"
            ).fetchone()[0]
            recent = con.execute(
                "SELECT COUNT(*) FROM history WHERE last_crawled_at > ?", (cutoff,)
            ).fetchone()[0]

            return {
                "total": total,
                "done": done,
                "failed": failed,
                "recent": recent,  # within recrawl threshold
            }
        finally:
            con.close()

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """
        Get domain counts in history.

        Returns:
            List of (domain, count) tuples ordered by count desc
        """
        con = get_connection(self.db_path)
        try:
            cur = con.execute(
                """
                SELECT domain, COUNT(*) as cnt
                FROM history
                WHERE status = 'done'
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]
        finally:
            con.close()
