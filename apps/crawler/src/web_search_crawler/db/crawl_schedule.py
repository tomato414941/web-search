"""Durable crawl schedule operations."""

from __future__ import annotations

import time
import uuid

from psycopg2.errors import DeadlockDetected, SerializationFailure

from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_types import CrawlTask
from web_search_core.urls import url_hash
from web_search_crawler.services.crawl_scheduling import (
    compute_admission_schedule,
    compute_failure_retry_delay_for_url,
    compute_success_recrawl_delay_for_url,
)
from web_search_postgres.search import sql_placeholder

_CRAWL_SCHEDULE_RETRY_LIMIT = 2
_CRAWL_SCHEDULE_RETRY_BASE_SEC = 0.05


class CrawlScheduleMixin:
    """Mixin for durable crawl task leasing and completion updates."""

    db_path: str
    recrawl_threshold: int

    def _reconcile_expired_crawl_task_leases(self, cur, *, now: int) -> int:
        """Return expired leases to pending and fix inflight counts."""
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT domain
            FROM crawl_schedule
            WHERE status = 'leased'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= {ph}
            """,
            (now,),
        )
        expired_domains = [row[0] for row in cur.fetchall()]
        if not expired_domains:
            return 0

        cur.execute(
            f"""
            UPDATE crawl_schedule
            SET
                status = 'pending',
                lease_token = NULL,
                lease_expires_at = NULL,
                updated_at = {ph}
            WHERE status = 'leased'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= {ph}
            """,
            (now, now),
        )
        if hasattr(self, "domain_scheduling_state"):
            self.domain_scheduling_state.adjust_inflight_leases(
                cur,
                expired_domains,
                delta=-1,
                now=now,
            )
        return len(expired_domains)

    def _select_ready_crawl_candidates(
        self,
        cur,
        *,
        now: int,
        overscan: int,
        max_per_domain: int,
    ) -> list[tuple]:
        """Select ready crawl task candidates from the durable schedule."""
        ph = sql_placeholder()
        where_clauses = [
            "task.status = 'pending'",
            f"task.next_fetch_at <= {ph}",
            (
                "(\n"
                "                  task.lease_expires_at IS NULL\n"
                f"                  OR task.lease_expires_at <= {ph}\n"
                "              )"
            ),
        ]
        params: list[object] = [now, now]
        params.extend([now, now, max(0, max_per_domain), overscan])
        cur.execute(
            f"""
            WITH active_leases AS (
                SELECT domain, COUNT(*)::INTEGER AS leased
                FROM crawl_schedule
                WHERE status = 'leased'
                GROUP BY domain
            )
            SELECT
                task.url_hash,
                task.url,
                task.domain,
                task.discovered_at,
                task.priority_bucket,
                task.next_fetch_at,
                COALESCE(active_leases.leased, 0),
                COALESCE(domain_state.next_request_at, 0),
                COALESCE(domain_state.backoff_until, 0)
            FROM crawl_schedule AS task
            LEFT JOIN domain_state ON domain_state.domain = task.domain
            LEFT JOIN active_leases ON active_leases.domain = task.domain
            WHERE {" AND ".join(where_clauses)}
              AND COALESCE(domain_state.next_request_at, 0) <= {ph}
              AND COALESCE(domain_state.backoff_until, 0) <= {ph}
              AND COALESCE(active_leases.leased, 0) < {ph}
            ORDER BY
                task.priority_bucket ASC,
                task.next_fetch_at ASC,
                task.last_success_at ASC NULLS FIRST,
                task.discovered_at ASC,
                task.url_hash ASC
            LIMIT {ph}
            FOR UPDATE OF task SKIP LOCKED
            """,
            params,
        )
        return cur.fetchall()

    @staticmethod
    def _choose_crawl_candidates(
        candidates: list[tuple],
        *,
        now: int,
        count: int,
        max_per_domain: int,
    ) -> list[tuple]:
        """Apply simple per-domain lease caps to an ordered candidate list."""
        selected = []
        leased_per_domain: dict[str, int] = {}
        for row in candidates:
            domain = row[2]
            inflight_leases = int(row[6] or 0)
            next_request_at = int(row[7] or 0)
            backoff_until = int(row[8] or 0)
            if next_request_at > now or backoff_until > now:
                continue
            effective_leases = inflight_leases + leased_per_domain.get(domain, 0)
            if effective_leases >= max_per_domain:
                continue
            selected.append(row)
            leased_per_domain[domain] = leased_per_domain.get(domain, 0) + 1
            if len(selected) >= count:
                break
        return selected

    def _mark_crawl_tasks_leased(
        self,
        cur,
        *,
        selected: list[tuple],
        lease_token: str,
        lease_expires_at: int,
        now: int,
    ) -> None:
        """Move selected crawl task rows into leased state."""
        if not selected:
            return
        ph = sql_placeholder()
        selected_hashes = [row[0] for row in selected]
        cur.execute(
            f"""
            UPDATE crawl_schedule
            SET
                status = 'leased',
                lease_token = {ph},
                lease_expires_at = {ph},
                updated_at = {ph}
            WHERE url_hash = ANY({ph})
            """,
            (lease_token, lease_expires_at, now, selected_hashes),
        )
        if hasattr(self, "domain_scheduling_state"):
            self.domain_scheduling_state.adjust_inflight_leases(
                cur,
                [row[2] for row in selected],
                delta=1,
                now=now,
            )

    def _lease_crawl_candidates(
        self,
        cur,
        *,
        now: int,
        count: int,
        max_per_domain: int,
        lease_token: str,
        lease_expires_at: int,
    ) -> list[tuple]:
        """Select and lease a bounded candidate set."""
        if count <= 0:
            return []

        overscan = max(count * max_per_domain * 6, count * 2)
        candidates = self._select_ready_crawl_candidates(
            cur,
            now=now,
            overscan=overscan,
            max_per_domain=max_per_domain,
        )
        selected = self._choose_crawl_candidates(
            candidates,
            now=now,
            count=count,
            max_per_domain=max_per_domain,
        )
        if selected:
            self._mark_crawl_tasks_leased(
                cur,
                selected=selected,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                now=now,
            )
        return selected

    def _update_crawl_task_after_result(
        self,
        cur,
        *,
        url_hash_value: str,
        status: str,
        next_fetch_at: int,
        last_fetched_at: int,
        last_success_at: int | None,
        next_fail_streak: int,
        now: int,
    ) -> int:
        """Persist the crawl task transition after a crawl attempt."""
        ph = sql_placeholder()
        cur.execute(
            f"""
            UPDATE crawl_schedule
            SET
                status = 'pending',
                next_fetch_at = {ph},
                last_fetched_at = {ph},
                last_success_at = CASE
                    WHEN {ph} IS NULL THEN last_success_at
                    ELSE {ph}
                END,
                last_status = {ph},
                fail_streak = {ph},
                lease_token = NULL,
                lease_expires_at = NULL,
                updated_at = {ph}
            WHERE url_hash = {ph}
            """,
            (
                next_fetch_at,
                last_fetched_at,
                last_success_at,
                last_success_at,
                status,
                next_fail_streak,
                now,
                url_hash_value,
            ),
        )
        return cur.rowcount

    def reconcile_expired_crawl_task_leases(self) -> int:
        """Return expired leased crawl tasks back to pending."""
        now = int(time.time())
        with db_transaction(self.db_path) as cur:
            return self._reconcile_expired_crawl_task_leases(cur, now=now)

    def lease_ready_crawl_tasks(
        self,
        count: int,
        *,
        max_per_domain: int = 3,
        lease_seconds: int = 300,
    ) -> list[CrawlTask]:
        """Lease ready crawl tasks with basic domain diversity."""
        if count <= 0:
            return []
        now = int(time.time())
        lease_token = uuid.uuid4().hex
        lease_expires_at = now + max(1, lease_seconds)
        selected: list[tuple] = []
        for attempt in range(_CRAWL_SCHEDULE_RETRY_LIMIT + 1):
            try:
                selected = []
                with db_transaction(self.db_path) as cur:
                    self._reconcile_expired_crawl_task_leases(cur, now=now)
                    selected = self._lease_crawl_candidates(
                        cur,
                        now=now,
                        count=count,
                        max_per_domain=max_per_domain,
                        lease_token=lease_token,
                        lease_expires_at=lease_expires_at,
                    )
                break
            except (DeadlockDetected, SerializationFailure):
                if attempt >= _CRAWL_SCHEDULE_RETRY_LIMIT:
                    raise
                time.sleep(_CRAWL_SCHEDULE_RETRY_BASE_SEC * (attempt + 1))

        if not selected:
            return []

        return [
            CrawlTask(url=row[1], domain=row[2], created_at=row[3]) for row in selected
        ]

    def release_crawl_tasks(
        self,
        urls: list[str],
        *,
        delay_seconds: int = 0,
        prefer_earlier: bool = False,
    ) -> int:
        """Release leased crawl tasks back to pending."""
        if not urls:
            return 0
        now = int(time.time())
        next_fetch_at = now + max(0, delay_seconds)
        hashes = [url_hash(url) for url in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain
                FROM crawl_schedule
                WHERE url_hash = ANY({sql_placeholder()})
                  AND status = 'leased'
                """,
                (hashes,),
            )
            leased_domains = [row[0] for row in cur.fetchall()]
            cur.execute(
                f"""
                UPDATE crawl_schedule
                SET
                    status = 'pending',
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    next_fetch_at = CASE
                        WHEN {sql_placeholder()} THEN LEAST(next_fetch_at, {sql_placeholder()})
                        ELSE GREATEST(next_fetch_at, {sql_placeholder()})
                    END,
                    updated_at = {sql_placeholder()}
                WHERE url_hash = ANY({sql_placeholder()})
                """,
                (prefer_earlier, next_fetch_at, next_fetch_at, now, hashes),
            )
            updated = cur.rowcount
            if (
                updated > 0
                and leased_domains
                and hasattr(self, "domain_scheduling_state")
            ):
                self.domain_scheduling_state.adjust_inflight_leases(
                    cur,
                    leased_domains,
                    delta=-1,
                    now=now,
                )
            return updated

    def record_crawl_task_result(self, url: str, status: str) -> None:
        """Persist crawl task completion state and next eligible fetch time."""
        now = int(time.time())
        h = url_hash(url)
        is_success = status == "done"

        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT
                    url,
                    domain,
                    fail_streak,
                    status
                FROM crawl_schedule
                WHERE url_hash = {sql_placeholder()}
                """,
                (h,),
            )
            row = cur.fetchone()
            if row is None:
                return

            url = row[0]
            domain = row[1]
            fail_streak = int(row[2] or 0)
            was_leased = row[3] == "leased"
            if is_success:
                reassigned = compute_admission_schedule(
                    url,
                    admission_intent="normal",
                )
                priority_bucket = reassigned.priority_bucket
            else:
                priority_bucket = None

            if is_success:
                next_delay = compute_success_recrawl_delay_for_url(url)
                next_fail_streak = 0
                last_success_at = now
            else:
                next_delay = compute_failure_retry_delay_for_url(
                    url,
                    fail_streak=fail_streak,
                )
                next_fail_streak = fail_streak + 1
                last_success_at = None

            self._update_crawl_task_after_result(
                cur,
                url_hash_value=h,
                status=status,
                next_fetch_at=now + next_delay,
                last_fetched_at=now,
                last_success_at=last_success_at,
                next_fail_streak=next_fail_streak,
                now=now,
            )
            if priority_bucket is not None:
                cur.execute(
                    f"""
                    UPDATE crawl_schedule
                    SET
                        priority_bucket = {sql_placeholder()},
                        updated_at = {sql_placeholder()}
                    WHERE url_hash = {sql_placeholder()}
                    """,
                    (
                        priority_bucket,
                        now,
                        h,
                    ),
                )
            if was_leased and hasattr(self, "domain_scheduling_state"):
                self.domain_scheduling_state.adjust_inflight_leases(
                    cur,
                    [domain],
                    delta=-1,
                    now=now,
                )
            if hasattr(self, "domain_scheduling_state"):
                self.domain_scheduling_state.record_crawl_result(
                    cur,
                    domain=domain,
                    is_success=is_success,
                    now=now,
                )
