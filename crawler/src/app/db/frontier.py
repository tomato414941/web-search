"""
Frontier - Pending URL Storage

Manages URLs that have been discovered but not yet crawled.
"""

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from shared.db.search import get_connection


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
class FrontierItem:
    url: str
    domain: str
    priority: float
    source_url: Optional[str]
    created_at: int


SCHEMA = """
CREATE TABLE IF NOT EXISTS frontier (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    priority REAL NOT NULL DEFAULT 0,
    source_url TEXT,
    created_at INTEGER NOT NULL
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_frontier_priority ON frontier(priority DESC);
CREATE INDEX IF NOT EXISTS idx_frontier_domain ON frontier(domain);
"""


class Frontier:
    """
    Pending URL storage.

    Stores URLs that have been discovered but not yet crawled.
    Uses SQLite for persistence.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
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

    def add(
        self,
        url: str,
        priority: float = 0.0,
        source_url: Optional[str] = None,
    ) -> bool:
        """
        Add a URL to the frontier.

        Args:
            url: URL to add
            priority: Priority score (higher = crawled sooner)
            source_url: URL where this link was discovered

        Returns:
            True if added, False if already exists
        """
        h = url_hash(url)
        domain = get_domain(url)
        now = int(time.time())

        con = get_connection(self.db_path)
        try:
            # INSERT OR IGNORE to handle duplicates
            cur = con.execute(
                """
                INSERT OR IGNORE INTO frontier (url_hash, url, domain, priority, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (h, url, domain, priority, source_url, now),
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def add_batch(
        self,
        urls: list[str],
        priority: float = 0.0,
        source_url: Optional[str] = None,
    ) -> int:
        """
        Add multiple URLs to the frontier.

        Args:
            urls: URLs to add
            priority: Priority score
            source_url: URL where these links were discovered

        Returns:
            Number of URLs added (excludes duplicates)
        """
        if not urls:
            return 0

        now = int(time.time())
        added = 0

        con = get_connection(self.db_path)
        try:
            for url in urls:
                h = url_hash(url)
                domain = get_domain(url)

                cur = con.execute(
                    """
                    INSERT OR IGNORE INTO frontier (url_hash, url, domain, priority, source_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (h, url, domain, priority, source_url, now),
                )
                if cur.rowcount > 0:
                    added += 1

            con.commit()
            return added
        finally:
            con.close()

    def pop(self) -> Optional[FrontierItem]:
        """
        Remove and return highest-priority URL.

        Returns:
            FrontierItem or None if empty
        """
        con = get_connection(self.db_path)
        try:
            # Select highest priority
            cur = con.execute(
                """
                SELECT url_hash, url, domain, priority, source_url, created_at
                FROM frontier
                ORDER BY priority DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return None

            url_hash_val, url, domain, priority, source_url, created_at = row

            # Delete it
            con.execute("DELETE FROM frontier WHERE url_hash = ?", (url_hash_val,))
            con.commit()

            return FrontierItem(
                url=url,
                domain=domain,
                priority=priority,
                source_url=source_url,
                created_at=created_at,
            )
        finally:
            con.close()

    def pop_batch(self, count: int) -> list[FrontierItem]:
        """
        Remove and return highest-priority URLs.

        Args:
            count: Maximum number of URLs to return

        Returns:
            List of FrontierItems
        """
        if count <= 0:
            return []

        con = get_connection(self.db_path)
        try:
            # Select highest priority
            cur = con.execute(
                """
                SELECT url_hash, url, domain, priority, source_url, created_at
                FROM frontier
                ORDER BY priority DESC
                LIMIT ?
                """,
                (count,),
            )
            rows = cur.fetchall()
            if not rows:
                return []

            items = []
            hashes = []
            for row in rows:
                url_hash_val, url, domain, priority, source_url, created_at = row
                hashes.append(url_hash_val)
                items.append(
                    FrontierItem(
                        url=url,
                        domain=domain,
                        priority=priority,
                        source_url=source_url,
                        created_at=created_at,
                    )
                )

            # Delete them
            placeholders = ",".join("?" * len(hashes))
            con.execute(
                f"DELETE FROM frontier WHERE url_hash IN ({placeholders})", hashes
            )
            con.commit()

            return items
        finally:
            con.close()

    def peek(self, count: int = 10) -> list[FrontierItem]:
        """
        View top URLs without removing them.

        Args:
            count: Number of URLs to return

        Returns:
            List of FrontierItems
        """
        con = get_connection(self.db_path)
        try:
            cur = con.execute(
                """
                SELECT url_hash, url, domain, priority, source_url, created_at
                FROM frontier
                ORDER BY priority DESC
                LIMIT ?
                """,
                (count,),
            )
            return [
                FrontierItem(
                    url=row[1],
                    domain=row[2],
                    priority=row[3],
                    source_url=row[4],
                    created_at=row[5],
                )
                for row in cur.fetchall()
            ]
        finally:
            con.close()

    def size(self) -> int:
        """Return number of URLs in frontier."""
        con = get_connection(self.db_path)
        try:
            cur = con.execute("SELECT COUNT(*) FROM frontier")
            return cur.fetchone()[0]
        finally:
            con.close()

    def contains(self, url: str) -> bool:
        """Check if URL is in frontier."""
        h = url_hash(url)
        con = get_connection(self.db_path)
        try:
            cur = con.execute("SELECT 1 FROM frontier WHERE url_hash = ?", (h,))
            return cur.fetchone() is not None
        finally:
            con.close()

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """
        Get domain counts in frontier.

        Returns:
            List of (domain, count) tuples ordered by count desc
        """
        con = get_connection(self.db_path)
        try:
            cur = con.execute(
                """
                SELECT domain, COUNT(*) as cnt
                FROM frontier
                GROUP BY domain
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]
        finally:
            con.close()
