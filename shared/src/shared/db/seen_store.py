"""
Hybrid Seen URL Store

Redis cache + SQLite persistence for visited URLs management.
Supports recrawling after configurable threshold.
"""

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Optional

import redis

SEEN_URLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_urls (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    crawl_count INTEGER DEFAULT 1
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_seen_last ON seen_urls(last_seen_at);
"""


class HybridSeenStore:
    """
    Hybrid URL seen checker with Redis cache + SQLite persistence.

    Redis: Fast cache (configurable TTL, default 7 days)
    SQLite: Source of truth (configurable recrawl window, default 30 days)
    """

    CACHE_KEY = "crawl:seen:cache"

    def __init__(
        self,
        redis_client: redis.Redis,
        db_path: str,
        cache_ttl_days: int = 7,
        recrawl_after_days: int = 30,
    ):
        self.redis = redis_client
        self.db_path = db_path
        self.cache_ttl = cache_ttl_days * 86400
        self.recrawl_threshold = recrawl_after_days * 86400
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with WAL mode."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SEEN_URLS_SCHEMA)

    @staticmethod
    def _hash_url(url: str) -> str:
        """Generate 16-character hash for URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def is_seen(self, url: str) -> bool:
        """
        Check if URL was seen within recrawl threshold.

        Returns:
            True if URL should be skipped (recently crawled)
            False if URL can be crawled (new or stale)
        """
        url_hash = self._hash_url(url)

        # 1. Redis cache (fast path)
        if self.redis.sismember(self.CACHE_KEY, url_hash):
            return True

        # 2. SQLite (source of truth)
        now = int(time.time())
        cutoff = now - self.recrawl_threshold

        with sqlite3.connect(self.db_path) as con:
            cur = con.execute(
                "SELECT last_seen_at FROM seen_urls WHERE url_hash = ? AND last_seen_at > ?",
                (url_hash, cutoff),
            )
            if cur.fetchone():
                # Warm up cache
                self.redis.sadd(self.CACHE_KEY, url_hash)
                self.redis.expire(self.CACHE_KEY, self.cache_ttl)
                return True

        return False

    def mark_seen(self, url: str):
        """Mark URL as seen in both Redis and SQLite."""
        url_hash = self._hash_url(url)
        now = int(time.time())

        # Redis cache
        self.redis.sadd(self.CACHE_KEY, url_hash)
        self.redis.expire(self.CACHE_KEY, self.cache_ttl)

        # SQLite persistent
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT INTO seen_urls (url_hash, url, first_seen_at, last_seen_at, crawl_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(url_hash) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    crawl_count = crawl_count + 1
            """,
                (url_hash, url, now, now),
            )

    def filter_unseen(self, urls: list[str]) -> list[str]:
        """
        Filter URLs to return only unseen ones.

        Args:
            urls: List of URLs to check

        Returns:
            List of URLs that are not recently seen (can be crawled)
        """
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        unseen = []

        with sqlite3.connect(self.db_path) as con:
            for url in urls:
                url_hash = self._hash_url(url)

                # Check Redis cache first (fast path)
                if self.redis.sismember(self.CACHE_KEY, url_hash):
                    continue

                # Check SQLite
                cur = con.execute(
                    "SELECT 1 FROM seen_urls WHERE url_hash = ? AND last_seen_at > ?",
                    (url_hash, cutoff),
                )
                if cur.fetchone():
                    # Warm up cache
                    self.redis.sadd(self.CACHE_KEY, url_hash)
                    continue

                unseen.append(url)

        if unseen:
            self.redis.expire(self.CACHE_KEY, self.cache_ttl)

        return unseen

    def mark_seen_batch(self, urls: list[str]) -> int:
        """
        Mark multiple URLs as seen.

        Args:
            urls: URLs to mark as seen

        Returns:
            Count of new URLs (not previously seen within threshold)
        """
        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        new_count = 0

        with sqlite3.connect(self.db_path) as con:
            for url in urls:
                url_hash = self._hash_url(url)

                # Check if recently seen
                cur = con.execute(
                    "SELECT 1 FROM seen_urls WHERE url_hash = ? AND last_seen_at > ?",
                    (url_hash, cutoff),
                )
                if cur.fetchone():
                    continue

                # Insert or update
                con.execute(
                    """
                    INSERT INTO seen_urls (url_hash, url, first_seen_at, last_seen_at, crawl_count)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(url_hash) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at,
                        crawl_count = crawl_count + 1
                """,
                    (url_hash, url, now, now),
                )

                self.redis.sadd(self.CACHE_KEY, url_hash)
                new_count += 1

        if new_count > 0:
            self.redis.expire(self.CACHE_KEY, self.cache_ttl)

        return new_count

    def get_stats(self) -> dict:
        """
        Get statistics about seen URLs.

        Returns:
            Dict with total_seen, active_seen, cache_size
        """
        with sqlite3.connect(self.db_path) as con:
            total = con.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0]
            now = int(time.time())
            cutoff = now - self.recrawl_threshold
            active = con.execute(
                "SELECT COUNT(*) FROM seen_urls WHERE last_seen_at > ?", (cutoff,)
            ).fetchone()[0]

        return {
            "total_seen": total,
            "active_seen": active,
            "cache_size": self.redis.scard(self.CACHE_KEY),
        }

    def get_url_info(self, url: str) -> Optional[dict]:
        """
        Get information about a specific URL.

        Returns:
            Dict with url, first_seen_at, last_seen_at, crawl_count or None
        """
        url_hash = self._hash_url(url)

        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.execute(
                "SELECT url, first_seen_at, last_seen_at, crawl_count FROM seen_urls WHERE url_hash = ?",
                (url_hash,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

        return None
