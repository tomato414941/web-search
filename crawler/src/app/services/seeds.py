"""
Seed Service

Manages seed URL storage and requeueing operations.
Seeds are stored in the database for persistence.
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from shared.db.search import get_connection, is_postgres_mode

from app.db.url_store import UrlStore
from app.core.config import settings
from app.domain.scoring import SEED_DEFAULT_SCORE
from app.models.seeds import SeedItem

logger = logging.getLogger(__name__)


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


SEEDS_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS seeds (
    url TEXT PRIMARY KEY,
    added_at INTEGER NOT NULL,
    last_queued INTEGER
);
"""

SEEDS_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS seeds (
    url TEXT PRIMARY KEY,
    added_at INTEGER NOT NULL,
    last_queued INTEGER
);
"""


class SeedService:
    """Seed URL management service"""

    def __init__(self, url_store: UrlStore):
        self.url_store = url_store
        self.db_path = settings.CRAWLER_DB_PATH
        self._init_db()

    def _init_db(self):
        """Initialize seeds table."""
        postgres_mode = is_postgres_mode()

        if not postgres_mode:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        con = get_connection(self.db_path)
        try:
            if postgres_mode:
                cur = con.cursor()
                cur.execute(SEEDS_SCHEMA_PG)
                # Drop legacy priority column if it exists
                cur.execute("ALTER TABLE seeds DROP COLUMN IF EXISTS priority")
                con.commit()
                cur.close()
            else:
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SEEDS_SCHEMA_SQLITE)
        finally:
            con.close()

    def list_seeds(self) -> list[SeedItem]:
        """
        Get all registered seeds.

        Returns:
            List of SeedItem objects
        """
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT url, added_at, last_queued FROM seeds ORDER BY added_at DESC"
            )
            result = []
            for row in cur.fetchall():
                url, added_at, last_queued = row
                result.append(
                    SeedItem(
                        url=url,
                        added_at=datetime.fromtimestamp(added_at),
                        last_queued=datetime.fromtimestamp(last_queued)
                        if last_queued
                        else None,
                    )
                )
            cur.close()
            return result
        finally:
            con.close()

    def add_seeds(self, urls: list[str], score: float = SEED_DEFAULT_SCORE) -> int:
        """
        Add URLs as seeds and queue them for crawling.

        Args:
            urls: List of URLs to add
            score: Queue priority score (internal constant, not user-specified)

        Returns:
            Number of new seeds added
        """
        now = int(time.time())
        added = 0
        ph = _placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                # Check if already exists
                cur.execute(f"SELECT 1 FROM seeds WHERE url = {ph}", (url,))
                if cur.fetchone() is None:
                    # New seed
                    cur.execute(
                        f"INSERT INTO seeds (url, added_at, last_queued) VALUES ({ph}, {ph}, {ph})",
                        (url, now, now),
                    )
                    added += 1
                else:
                    # Update last_queued for existing seed
                    cur.execute(
                        f"UPDATE seeds SET last_queued = {ph} WHERE url = {ph}",
                        (now, url),
                    )

            con.commit()
            cur.close()
        finally:
            con.close()

        # add_batch handles dedup + recrawl check internally
        self.url_store.add_batch(urls, priority=score)

        logger.info(f"Added {added} new seeds")
        return added

    def delete_seeds(self, urls: list[str]) -> int:
        """
        Remove URLs from seed list.

        Args:
            urls: List of URLs to remove

        Returns:
            Number of seeds removed
        """
        deleted = 0
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            for url in urls:
                cur.execute(f"DELETE FROM seeds WHERE url = {ph}", (url,))
                deleted += cur.rowcount
            con.commit()
            cur.close()
        finally:
            con.close()

        logger.info(f"Deleted {deleted} seeds")
        return deleted

    def requeue_all(self, force: bool = False) -> int:
        """
        Re-add all seeds to the crawl queue.

        Args:
            force: If True, add even if recently crawled

        Returns:
            Number of URLs queued
        """
        now = int(time.time())
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT url FROM seeds")
            seed_urls = [row[0] for row in cur.fetchall()]

            # Update last_queued for all
            cur.execute(f"UPDATE seeds SET last_queued = {ph}", (now,))
            con.commit()
            cur.close()
        finally:
            con.close()

        if not seed_urls:
            return 0

        # Add to url_store (add_batch handles dedup internally)
        queued = 0
        for url in seed_urls:
            if force or not self.url_store.is_recently_crawled(url):
                if self.url_store.add(url, priority=SEED_DEFAULT_SCORE):
                    queued += 1

        logger.info(f"Requeued {queued} seeds (force={force})")
        return queued

    def requeue_one(self, url: str, force: bool = False) -> bool:
        """
        Re-add a specific seed to the crawl queue.

        Args:
            url: URL to requeue
            force: If True, add even if recently crawled

        Returns:
            True if URL was queued
        """
        now = int(time.time())
        ph = _placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(f"SELECT 1 FROM seeds WHERE url = {ph}", (url,))
            row = cur.fetchone()
            if not row:
                cur.close()
                return False

            # Update last_queued
            cur.execute(
                f"UPDATE seeds SET last_queued = {ph} WHERE url = {ph}", (now, url)
            )
            con.commit()
            cur.close()
        finally:
            con.close()

        # Check if can add
        if not force and self.url_store.is_recently_crawled(url):
            return False

        return self.url_store.add(url, priority=SEED_DEFAULT_SCORE)
