"""URL ledger persistence."""

import logging
import os
import time
from collections.abc import Iterable
from typing import Any

from psycopg2.errors import DeadlockDetected, SerializationFailure
from psycopg2.extras import execute_values

from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_types import get_domain, url_hash
from web_search_crawler.services.url_admission import URLAdmissionPolicy

logger = logging.getLogger(__name__)

_URL_LEDGER_CHUNK_SIZE = int(os.getenv("CRAWL_ENQUEUE_CHUNK_SIZE", "100"))
_URL_LEDGER_RETRY_LIMIT = int(os.getenv("CRAWL_ENQUEUE_RETRY_LIMIT", "2"))
_URL_LEDGER_RETRY_BASE_SEC = float(os.getenv("CRAWL_ENQUEUE_RETRY_BASE_SEC", "0.05"))


class UrlLedgerStore:
    """Persistent ledger of URLs known to the project."""

    def __init__(self, db_path: str, url_admission_policy: URLAdmissionPolicy):
        self.db_path = db_path
        self.url_admission_policy = url_admission_policy

    @staticmethod
    def _chunked(
        seq: list[dict[str, Any]], size: int
    ) -> Iterable[list[dict[str, Any]]]:
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

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
        """Record discovered URLs in the urls ledger."""
        if not urls:
            return 0
        rows = self._normalize_known_urls(urls)
        if not rows:
            return 0

        now = int(time.time())
        chunk_size = max(1, _URL_LEDGER_CHUNK_SIZE)

        recorded = 0
        for chunk in self._chunked(rows, chunk_size):
            for attempt in range(_URL_LEDGER_RETRY_LIMIT + 1):
                try:
                    with db_transaction(self.db_path) as cur:
                        recorded += self._insert_urls_batch(cur, chunk, now=now)
                    break
                except (DeadlockDetected, SerializationFailure):
                    if attempt >= _URL_LEDGER_RETRY_LIMIT:
                        raise
                    delay = _URL_LEDGER_RETRY_BASE_SEC * (attempt + 1)
                    logger.warning(
                        "Retrying URL ledger chunk after DB concurrency error "
                        "(attempt %d/%d, chunk=%d, delay=%.2fs)",
                        attempt + 1,
                        _URL_LEDGER_RETRY_LIMIT,
                        len(chunk),
                        delay,
                    )
                    time.sleep(delay)

        return recorded
