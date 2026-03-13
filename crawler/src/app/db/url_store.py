"""
URL Store - Discovery Ledger + Crawl Queue

urls table: ledger of all discovered URLs (no status column).
crawl_queue table: work queue of URLs to crawl next (DELETE on pop).
"""

import os
import time
from collections.abc import Iterable

from app.db.url_discovery import UrlDiscoveryMixin
from app.db.url_queries import UrlQueriesMixin
from app.db.url_queue import UrlQueueMixin
from app.db.url_seeds import UrlSeedsMixin
from shared.postgres.search import get_connection


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    url_hash        TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    domain          TEXT NOT NULL,
    crawl_count     INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL,
    last_crawled_at INTEGER,
    is_seed         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain);

CREATE TABLE IF NOT EXISTS crawl_queue (
    url_hash   TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    domain     TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


class UrlStore(UrlDiscoveryMixin, UrlQueueMixin, UrlQueriesMixin, UrlSeedsMixin):
    """
    URL storage backed by a discovery ledger (urls) and a crawl queue.

    urls: all discovered URLs. last_crawled_at IS NULL means never crawled.
    crawl_queue: URLs waiting to be crawled. Popped via DELETE.
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
        self._pending_count_cache_ttl_sec = int(
            os.getenv("CRAWL_PENDING_COUNT_CACHE_TTL_SEC", "30")
        )
        self._pending_count_cache: dict[str, tuple[int, float]] = {}
        self._init_db()

    def _init_db(self):
        # Schema is managed by Alembic; verify connectivity only.
        con = get_connection(self.db_path)
        con.close()

    def _get_cached_pending_counts(
        self, domains: Iterable[str]
    ) -> tuple[dict[str, int], list[str]]:
        now = time.time()
        cached: dict[str, int] = {}
        missing: list[str] = []
        for domain in domains:
            entry = self._pending_count_cache.get(domain)
            if entry is None or now - entry[1] >= self._pending_count_cache_ttl_sec:
                missing.append(domain)
                continue
            cached[domain] = entry[0]
        return cached, missing

    def _set_cached_pending_counts(self, counts: dict[str, int]) -> None:
        now = time.time()
        for domain, count in counts.items():
            self._pending_count_cache[domain] = (max(0, count), now)

    def _bump_cached_pending_count(self, domain: str, delta: int) -> None:
        entry = self._pending_count_cache.get(domain)
        if entry is None:
            return
        self._pending_count_cache[domain] = (
            max(0, entry[0] + delta),
            time.time(),
        )

    def _drop_cached_pending_counts(self, domains: Iterable[str]) -> None:
        for domain in domains:
            self._pending_count_cache.pop(domain, None)
