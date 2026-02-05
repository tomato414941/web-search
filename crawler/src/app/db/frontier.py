"""
Frontier - Pending URL Storage

Manages URLs that have been discovered but not yet crawled.
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
class FrontierItem:
    url: str
    domain: str
    priority: float
    source_url: Optional[str]
    created_at: int


SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS frontier (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    priority REAL NOT NULL DEFAULT 0,
    source_url TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_frontier_priority ON frontier(priority DESC);
CREATE INDEX IF NOT EXISTS idx_frontier_domain ON frontier(domain);
"""

SCHEMA_SQLITE = """
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
    Uses PostgreSQL or SQLite for persistence.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database."""
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
        ph = _placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO frontier (url_hash, url, domain, priority, source_url, created_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT (url_hash) DO NOTHING
                    """,
                    (h, url, domain, priority, source_url, now),
                )
            else:
                cur.execute(
                    f"""
                    INSERT OR IGNORE INTO frontier (url_hash, url, domain, priority, source_url, created_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (h, url, domain, priority, source_url, now),
                )
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
                        INSERT INTO frontier (url_hash, url, domain, priority, source_url, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        ON CONFLICT (url_hash) DO NOTHING
                        """,
                        (h, url, domain, priority, source_url, now),
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT OR IGNORE INTO frontier (url_hash, url, domain, priority, source_url, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        """,
                        (h, url, domain, priority, source_url, now),
                    )
                if cur.rowcount > 0:
                    added += 1

            con.commit()
            cur.close()
            return added
        finally:
            con.close()

    def pop(self) -> Optional[FrontierItem]:
        """
        Remove and return highest-priority URL.

        Returns:
            FrontierItem or None if empty
        """
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            # Select highest priority
            cur.execute(
                """
                SELECT url_hash, url, domain, priority, source_url, created_at
                FROM frontier
                ORDER BY priority DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                cur.close()
                return None

            url_hash_val, url, domain, priority, source_url, created_at = row

            # Delete it
            cur.execute(f"DELETE FROM frontier WHERE url_hash = {ph}", (url_hash_val,))
            con.commit()
            cur.close()

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

        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            # Select highest priority
            cur.execute(
                f"""
                SELECT url_hash, url, domain, priority, source_url, created_at
                FROM frontier
                ORDER BY priority DESC
                LIMIT {ph}
                """,
                (count,),
            )
            rows = cur.fetchall()
            if not rows:
                cur.close()
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
            placeholders = ",".join(ph for _ in hashes)
            cur.execute(
                f"DELETE FROM frontier WHERE url_hash IN ({placeholders})",
                tuple(hashes),
            )
            con.commit()
            cur.close()

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
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT url_hash, url, domain, priority, source_url, created_at
                FROM frontier
                ORDER BY priority DESC
                LIMIT {ph}
                """,
                (count,),
            )
            result = [
                FrontierItem(
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

    def size(self) -> int:
        """Return number of URLs in frontier."""
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM frontier")
            result = cur.fetchone()[0]
            cur.close()
            return result
        finally:
            con.close()

    def contains(self, url: str) -> bool:
        """Check if URL is in frontier."""
        h = url_hash(url)
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(f"SELECT 1 FROM frontier WHERE url_hash = {ph}", (h,))
            result = cur.fetchone() is not None
            cur.close()
            return result
        finally:
            con.close()

    def get_domains(self, limit: int = 100) -> list[tuple[str, int]]:
        """
        Get domain counts in frontier.

        Returns:
            List of (domain, count) tuples ordered by count desc
        """
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT domain, COUNT(*) as cnt
                FROM frontier
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
