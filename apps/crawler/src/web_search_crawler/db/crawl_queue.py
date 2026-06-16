"""Pure crawl queue operations."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from psycopg2.errors import DeadlockDetected, SerializationFailure
from psycopg2.extras import execute_values

from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_types import CrawlTask
from web_search_core.urls import get_domain, url_hash
from web_search_postgres.search import sql_placeholder

_CRAWL_QUEUE_RETRY_LIMIT = 2
_CRAWL_QUEUE_RETRY_BASE_SEC = 0.05
_CRAWL_QUEUE_ADMISSION_CHUNK_SIZE = 100


class CrawlQueueMixin:
    """Mixin for enqueueing and popping crawl work."""

    db_path: str

    @staticmethod
    def _chunked(
        seq: list[dict[str, Any]], size: int
    ) -> Iterable[list[dict[str, Any]]]:
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    def _normalize_batch_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for url in urls:
            decision = self.url_admission_policy.evaluate(url)
            if decision.action != "allow" or not decision.normalized_url:
                continue
            normalized_url = decision.normalized_url
            h = url_hash(normalized_url)
            records.setdefault(
                h,
                {
                    "h": h,
                    "url": normalized_url,
                    "domain": get_domain(normalized_url),
                },
            )
        return sorted(records.values(), key=lambda row: row["h"])

    def _insert_crawl_queue_batch(
        self, cur: Any, rows: list[dict[str, Any]], now: int
    ) -> int:
        if not rows:
            return 0
        result = execute_values(
            cur,
            """
            INSERT INTO crawl_queue (url_hash, url, domain, created_at)
            VALUES %s
            ON CONFLICT (url_hash) DO NOTHING
            RETURNING url_hash
            """,
            [(row["h"], row["url"], row["domain"], now) for row in rows],
            fetch=True,
        )
        if hasattr(self, "domain_scheduling_state"):
            self.domain_scheduling_state.ensure_domain_state_rows(
                cur,
                [row["domain"] for row in rows],
                now=now,
            )
        return len(result)

    def _enqueue_urls_for_crawl_chunk(
        self,
        cur: Any,
        rows: list[dict[str, Any]],
        *,
        now: int,
    ) -> int:
        return self._insert_crawl_queue_batch(cur, rows, now)

    def enqueue_url_for_crawl(self, url: str) -> bool:
        """Add a known URL to the crawl queue."""
        return self.enqueue_urls_for_crawl([url]) > 0

    def enqueue_urls_for_crawl(self, urls: list[str]) -> int:
        """Add known URLs to the crawl queue if eligible."""
        if not urls:
            return 0
        rows = self._normalize_batch_urls(urls)
        if not rows:
            return 0

        now = int(time.time())
        chunk_size = max(1, _CRAWL_QUEUE_ADMISSION_CHUNK_SIZE)

        added = 0
        for chunk in self._chunked(rows, chunk_size):
            for attempt in range(_CRAWL_QUEUE_RETRY_LIMIT + 1):
                try:
                    with db_transaction(self.db_path) as cur:
                        added += self._enqueue_urls_for_crawl_chunk(
                            cur,
                            chunk,
                            now=now,
                        )
                    break
                except (DeadlockDetected, SerializationFailure):
                    if attempt >= _CRAWL_QUEUE_RETRY_LIMIT:
                        raise
                    time.sleep(_CRAWL_QUEUE_RETRY_BASE_SEC * (attempt + 1))

        return added

    def _select_crawl_queue_candidates(
        self,
        cur: Any,
        *,
        now: int,
        overscan: int,
    ) -> list[tuple]:
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT
                q.url_hash,
                q.url,
                q.domain,
                q.created_at,
                COALESCE(ds.next_request_at, 0),
                COALESCE(ds.backoff_until, 0)
            FROM crawl_queue AS q
            LEFT JOIN domain_state AS ds ON ds.domain = q.domain
            WHERE COALESCE(ds.next_request_at, 0) <= {ph}
              AND COALESCE(ds.backoff_until, 0) <= {ph}
            ORDER BY q.created_at ASC, q.url_hash ASC
            LIMIT {ph}
            FOR UPDATE OF q SKIP LOCKED
            """,
            (now, now, overscan),
        )
        return cur.fetchall()

    @staticmethod
    def _choose_crawl_queue_candidates(
        candidates: list[tuple],
        *,
        count: int,
        max_per_domain: int,
    ) -> list[tuple]:
        selected = []
        selected_per_domain: dict[str, int] = {}
        for row in candidates:
            domain = row[2]
            selected_for_domain = selected_per_domain.get(domain, 0)
            if selected_for_domain >= max_per_domain:
                continue
            selected.append(row)
            selected_per_domain[domain] = selected_for_domain + 1
            if len(selected) >= count:
                break
        return selected

    def pop_ready_crawl_tasks(
        self,
        count: int,
        *,
        max_per_domain: int = 3,
    ) -> list[CrawlTask]:
        """Atomically remove ready crawl tasks from the queue."""
        if count <= 0:
            return []
        now = int(time.time())
        selected: list[tuple] = []
        for attempt in range(_CRAWL_QUEUE_RETRY_LIMIT + 1):
            try:
                with db_transaction(self.db_path) as cur:
                    overscan = max(count * max_per_domain * 6, count * 2)
                    candidates = self._select_crawl_queue_candidates(
                        cur,
                        now=now,
                        overscan=overscan,
                    )
                    selected = self._choose_crawl_queue_candidates(
                        candidates,
                        count=count,
                        max_per_domain=max_per_domain,
                    )
                    if selected:
                        cur.execute(
                            f"""
                            DELETE FROM crawl_queue
                            WHERE url_hash = ANY({sql_placeholder()})
                            """,
                            ([row[0] for row in selected],),
                        )
                break
            except (DeadlockDetected, SerializationFailure):
                if attempt >= _CRAWL_QUEUE_RETRY_LIMIT:
                    raise
                time.sleep(_CRAWL_QUEUE_RETRY_BASE_SEC * (attempt + 1))

        return [
            CrawlTask(url=row[1], domain=row[2], created_at=row[3]) for row in selected
        ]

    def record_crawl_task_result(self, url: str, status: str) -> None:
        """Persist domain-level result state after a popped crawl task finishes."""
        now = int(time.time())
        domain = get_domain(url)
        is_success = status == "done"
        if not hasattr(self, "domain_scheduling_state"):
            return
        with db_transaction(self.db_path) as cur:
            self.domain_scheduling_state.record_crawl_result(
                cur,
                domain=domain,
                is_success=is_success,
                now=now,
            )
