"""URL discovery ledger operations and frontier admission."""

import logging
import os
import time
from collections.abc import Iterable
from typing import Any

from psycopg2.errors import DeadlockDetected, SerializationFailure
from psycopg2.extras import execute_values

from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_types import get_domain, url_hash
from web_search_crawler.services.crawl_policy import assign_crawl_policy
from web_search_postgres.search import sql_placeholder

logger = logging.getLogger(__name__)

_FRONTIER_ADMISSION_CHUNK_SIZE = int(os.getenv("CRAWL_ENQUEUE_CHUNK_SIZE", "100"))
_FRONTIER_ADMISSION_RETRY_LIMIT = int(os.getenv("CRAWL_ENQUEUE_RETRY_LIMIT", "2"))
_FRONTIER_ADMISSION_RETRY_BASE_SEC = float(
    os.getenv("CRAWL_ENQUEUE_RETRY_BASE_SEC", "0.05")
)


class UrlDiscoveryMixin:
    """Mixin for discovered-URL upserts and crawl ledger updates."""

    db_path: str
    recrawl_threshold: int

    @staticmethod
    def _chunked(
        seq: list[dict[str, Any]], size: int
    ) -> Iterable[list[dict[str, Any]]]:
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    def _normalize_batch_urls(
        self,
        urls: list[str],
        *,
        admission_intent: str,
        discovery_depth: int,
    ) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for url in urls:
            decision = self.url_admission_policy.evaluate(url)
            if decision.action != "allow" or not decision.normalized_url:
                continue
            normalized_url = decision.normalized_url
            h = url_hash(normalized_url)
            policy = assign_crawl_policy(
                normalized_url,
                admission_intent=admission_intent,
            )
            records.setdefault(
                h,
                {
                    "h": h,
                    "url": normalized_url,
                    "domain": get_domain(normalized_url),
                    "normalized_url": normalized_url,
                    "discovery_depth": discovery_depth,
                    "canonical_source": policy.canonical_source,
                    "crawl_profile": policy.crawl_profile,
                    "priority_bucket": policy.priority_bucket,
                    "priority_score": policy.priority_score,
                    "next_fetch_at": int(time.time())
                    + policy.initial_next_fetch_delay_sec,
                },
            )
        return sorted(records.values(), key=lambda row: row["h"])

    def _normalize_known_urls(
        self,
        urls: list[str],
    ) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for url in urls:
            if not url:
                continue
            decision = self.url_admission_policy.evaluate(url)
            known_url = decision.normalized_url or url
            h = url_hash(known_url)
            records.setdefault(
                h,
                {
                    "h": h,
                    "url": known_url,
                    "domain": get_domain(known_url),
                },
            )
        return sorted(records.values(), key=lambda row: row["h"])

    def _insert_urls_batch(self, cur: Any, rows: list[dict[str, Any]], now: int) -> int:
        if not rows:
            return 0
        result = execute_values(
            cur,
            """
            INSERT INTO urls (url_hash, url, domain, created_at)
            VALUES %s
            ON CONFLICT (url_hash) DO NOTHING
            RETURNING url_hash
            """,
            [
                (
                    row["h"],
                    row["url"],
                    row["domain"],
                    now,
                )
                for row in rows
            ],
            fetch=True,
        )
        return len(result)

    def _get_recently_fetched_frontier_hashes(
        self, cur: Any, hashes: list[str], cutoff: int
    ) -> set[str]:
        if not hashes:
            return set()
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT url_hash
            FROM frontier_entries
            WHERE url_hash = ANY({ph})
              AND last_fetched_at IS NOT NULL
              AND last_fetched_at >= {ph}
            """,
            (hashes, cutoff),
        )
        return {row[0] for row in cur.fetchall()}

    def _get_existing_frontier_hashes(
        self,
        cur: Any,
        hashes: list[str],
    ) -> set[str]:
        if not hashes:
            return set()
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT url_hash
            FROM frontier_entries
            WHERE url_hash = ANY({ph})
            """,
            (hashes,),
        )
        return {row[0] for row in cur.fetchall()}

    def _upsert_frontier_batch(
        self, cur: Any, rows: list[dict[str, Any]], now: int
    ) -> None:
        if not rows:
            return
        execute_values(
            cur,
            """
            INSERT INTO frontier_entries (
                url_hash,
                url,
                domain,
                normalized_url,
                discovered_at,
                discovery_depth,
                canonical_source,
                crawl_profile,
                priority_bucket,
                priority_score,
                status,
                next_fetch_at,
                updated_at
            )
            VALUES %s
            ON CONFLICT (url_hash) DO UPDATE SET
                url = EXCLUDED.url,
                domain = EXCLUDED.domain,
                normalized_url = EXCLUDED.normalized_url,
                discovery_depth = LEAST(
                    frontier_entries.discovery_depth,
                    EXCLUDED.discovery_depth
                ),
                canonical_source = COALESCE(
                    frontier_entries.canonical_source,
                    EXCLUDED.canonical_source
                ),
                crawl_profile = EXCLUDED.crawl_profile,
                priority_bucket = LEAST(
                    frontier_entries.priority_bucket,
                    EXCLUDED.priority_bucket
                ),
                priority_score = GREATEST(
                    frontier_entries.priority_score,
                    EXCLUDED.priority_score
                ),
                next_fetch_at = LEAST(
                    frontier_entries.next_fetch_at,
                    EXCLUDED.next_fetch_at
                ),
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row["h"],
                    row["url"],
                    row["domain"],
                    row["normalized_url"],
                    now,
                    row["discovery_depth"],
                    row["canonical_source"],
                    row["crawl_profile"],
                    row["priority_bucket"],
                    row["priority_score"],
                    "pending",
                    row["next_fetch_at"],
                    now,
                )
                for row in rows
            ],
        )

    def _record_discovered_urls_chunk(
        self,
        cur: Any,
        rows: list[dict[str, Any]],
        *,
        now: int,
    ) -> int:
        return self._insert_urls_batch(cur, rows, now)

    def _admit_urls_to_frontier_chunk(
        self,
        cur: Any,
        rows: list[dict[str, Any]],
        *,
        now: int,
        cutoff: int,
    ) -> int:
        recent_hashes = self._get_recently_fetched_frontier_hashes(
            cur, [row["h"] for row in rows], cutoff
        )
        admit_rows: list[dict[str, Any]] = []
        for row in rows:
            if row["h"] in recent_hashes:
                continue
            admit_rows.append(row)

        existing_frontier_hashes = self._get_existing_frontier_hashes(
            cur,
            [row["h"] for row in admit_rows],
        )
        self._upsert_frontier_batch(cur, admit_rows, now)
        if admit_rows and hasattr(self, "domain_scheduling_state"):
            self.domain_scheduling_state.ensure_domain_state_rows(
                cur,
                [row["domain"] for row in admit_rows],
                now=now,
            )
        if not admit_rows:
            return 0

        added = 0
        for row in admit_rows:
            if row["h"] in existing_frontier_hashes:
                continue
            added += 1
        return added

    def record_discovered_url(
        self,
        url: str,
    ) -> bool:
        """Record a discovered URL in the urls ledger only."""
        return (
            self.record_discovered_urls(
                [url],
            )
            > 0
        )

    def record_discovered_urls(
        self,
        urls: list[str],
    ) -> int:
        """Record discovered URLs in the urls ledger without frontier admission."""
        if not urls:
            return 0
        rows = self._normalize_known_urls(urls)
        if not rows:
            return 0

        now = int(time.time())
        chunk_size = max(1, _FRONTIER_ADMISSION_CHUNK_SIZE)

        recorded = 0
        for chunk in self._chunked(rows, chunk_size):
            for attempt in range(_FRONTIER_ADMISSION_RETRY_LIMIT + 1):
                try:
                    with db_transaction(self.db_path) as cur:
                        recorded += self._record_discovered_urls_chunk(
                            cur,
                            chunk,
                            now=now,
                        )
                    break
                except (DeadlockDetected, SerializationFailure):
                    if attempt >= _FRONTIER_ADMISSION_RETRY_LIMIT:
                        raise
                    delay = _FRONTIER_ADMISSION_RETRY_BASE_SEC * (attempt + 1)
                    logger.warning(
                        "Retrying URL discovery chunk after DB concurrency error "
                        "(attempt %d/%d, chunk=%d, delay=%.2fs)",
                        attempt + 1,
                        _FRONTIER_ADMISSION_RETRY_LIMIT,
                        len(chunk),
                        delay,
                    )
                    time.sleep(delay)

        return recorded

    def admit_url_to_frontier(
        self,
        url: str,
        *,
        admission_intent: str = "normal",
        discovery_depth: int = 1,
    ) -> bool:
        """Admit a URL into the frontier without writing the urls ledger."""
        return (
            self.admit_urls_to_frontier(
                [url],
                admission_intent=admission_intent,
                discovery_depth=discovery_depth,
            )
            > 0
        )

    def admit_urls_to_frontier(
        self,
        urls: list[str],
        *,
        admission_intent: str = "normal",
        discovery_depth: int = 1,
    ) -> int:
        """Admit URLs into the crawl frontier if eligible."""
        if not urls:
            return 0
        rows = self._normalize_batch_urls(
            urls,
            admission_intent=admission_intent,
            discovery_depth=discovery_depth,
        )
        if not rows:
            return 0

        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        chunk_size = max(1, _FRONTIER_ADMISSION_CHUNK_SIZE)

        added = 0
        for chunk in self._chunked(rows, chunk_size):
            for attempt in range(_FRONTIER_ADMISSION_RETRY_LIMIT + 1):
                try:
                    with db_transaction(self.db_path) as cur:
                        added += self._admit_urls_to_frontier_chunk(
                            cur,
                            chunk,
                            now=now,
                            cutoff=cutoff,
                        )
                    break
                except (DeadlockDetected, SerializationFailure):
                    if attempt >= _FRONTIER_ADMISSION_RETRY_LIMIT:
                        raise
                    delay = _FRONTIER_ADMISSION_RETRY_BASE_SEC * (attempt + 1)
                    logger.warning(
                        "Retrying frontier admission chunk after DB concurrency error "
                        "(attempt %d/%d, chunk=%d, delay=%.2fs)",
                        attempt + 1,
                        _FRONTIER_ADMISSION_RETRY_LIMIT,
                        len(chunk),
                        delay,
                    )
                    time.sleep(delay)

        return added

    def discover_and_admit_url(
        self,
        url: str,
        *,
        admission_intent: str = "normal",
        discovery_depth: int = 1,
    ) -> bool:
        """Record a URL in the ledger and admit it into the frontier."""
        return (
            self.discover_and_admit_urls(
                [url],
                admission_intent=admission_intent,
                discovery_depth=discovery_depth,
            )
            > 0
        )

    def discover_and_admit_urls(
        self,
        urls: list[str],
        *,
        admission_intent: str = "normal",
        discovery_depth: int = 1,
    ) -> int:
        """Record discovered URLs and admit them into the frontier if eligible."""
        if not urls:
            return 0
        rows = self._normalize_batch_urls(
            urls,
            admission_intent=admission_intent,
            discovery_depth=discovery_depth,
        )
        if not rows:
            return 0

        now = int(time.time())
        cutoff = now - self.recrawl_threshold
        chunk_size = max(1, _FRONTIER_ADMISSION_CHUNK_SIZE)

        added = 0
        for chunk in self._chunked(rows, chunk_size):
            for attempt in range(_FRONTIER_ADMISSION_RETRY_LIMIT + 1):
                try:
                    with db_transaction(self.db_path) as cur:
                        self._record_discovered_urls_chunk(cur, chunk, now=now)
                        added += self._admit_urls_to_frontier_chunk(
                            cur,
                            chunk,
                            now=now,
                            cutoff=cutoff,
                        )
                    break
                except (DeadlockDetected, SerializationFailure):
                    if attempt >= _FRONTIER_ADMISSION_RETRY_LIMIT:
                        raise
                    delay = _FRONTIER_ADMISSION_RETRY_BASE_SEC * (attempt + 1)
                    logger.warning(
                        "Retrying URL discovery/admission chunk after DB concurrency "
                        "error (attempt %d/%d, chunk=%d, delay=%.2fs)",
                        attempt + 1,
                        _FRONTIER_ADMISSION_RETRY_LIMIT,
                        len(chunk),
                        delay,
                    )
                    time.sleep(delay)

        return added

    def record_crawl_result(self, url: str, status: str) -> None:
        """Record a crawl result and update frontier state."""
        self.record_frontier_result(url, status)
