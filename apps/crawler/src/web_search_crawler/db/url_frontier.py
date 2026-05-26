"""Durable frontier operations for crawl planning."""

from __future__ import annotations

import time
import uuid

from psycopg2.errors import DeadlockDetected, SerializationFailure

from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_types import UrlItem, url_hash
from web_search_crawler.services.crawl_policy import (
    POLICIES,
    assign_crawl_policy,
    compute_failure_retry_delay,
    compute_success_recrawl_delay,
)
from web_search_crawler.services.frontier_budget import allocate_frontier_tier_budgets
from web_search_postgres.search import sql_placeholder

_FRONTIER_RETRY_LIMIT = 2
_FRONTIER_RETRY_BASE_SEC = 0.05


class UrlFrontierMixin:
    """Mixin for durable frontier leasing and completion updates."""

    db_path: str
    recrawl_threshold: int

    def _reconcile_expired_frontier_leases(self, cur, *, now: int) -> int:
        """Return expired leases to pending and fix inflight counts."""
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT domain
            FROM frontier_entries
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
            UPDATE frontier_entries
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

    def _select_ready_frontier_candidates(
        self,
        cur,
        *,
        now: int,
        overscan: int,
        max_per_domain: int,
        crawl_profiles: tuple[str, ...] | None = None,
    ) -> list[tuple]:
        """Select ready frontier candidates from the durable frontier."""
        ph = sql_placeholder()
        where_clauses = [
            "frontier.status = 'pending'",
            f"frontier.next_fetch_at <= {ph}",
            (
                "(\n"
                "                  frontier.lease_expires_at IS NULL\n"
                f"                  OR frontier.lease_expires_at <= {ph}\n"
                "              )"
            ),
        ]
        params: list[object] = [now, now]
        if crawl_profiles:
            where_clauses.append(f"frontier.crawl_profile = ANY({ph})")
            params.append(list(crawl_profiles))
        params.extend([now, now, max(0, max_per_domain), overscan])
        cur.execute(
            f"""
            WITH active_leases AS (
                SELECT domain, COUNT(*)::INTEGER AS leased
                FROM frontier_entries
                WHERE status = 'leased'
                GROUP BY domain
            )
            SELECT
                frontier.url_hash,
                frontier.url,
                frontier.domain,
                frontier.discovered_at,
                frontier.priority_bucket,
                frontier.priority_score,
                frontier.next_fetch_at,
                COALESCE(active_leases.leased, 0),
                COALESCE(domain_state.next_request_at, 0),
                COALESCE(domain_state.backoff_until, 0)
            FROM frontier_entries AS frontier
            LEFT JOIN domain_state ON domain_state.domain = frontier.domain
            LEFT JOIN active_leases ON active_leases.domain = frontier.domain
            WHERE {" AND ".join(where_clauses)}
              AND COALESCE(domain_state.next_request_at, 0) <= {ph}
              AND COALESCE(domain_state.backoff_until, 0) <= {ph}
              AND COALESCE(active_leases.leased, 0) < {ph}
            ORDER BY
                frontier.priority_bucket ASC,
                frontier.priority_score DESC,
                frontier.next_fetch_at ASC,
                frontier.last_success_at ASC NULLS FIRST,
                frontier.discovered_at ASC,
                frontier.url_hash ASC
            LIMIT {ph}
            FOR UPDATE OF frontier SKIP LOCKED
            """,
            params,
        )
        return cur.fetchall()

    @staticmethod
    def _choose_frontier_candidates(
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
            inflight_leases = int(row[7] or 0)
            next_request_at = int(row[8] or 0)
            backoff_until = int(row[9] or 0)
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

    def _mark_frontier_entries_leased(
        self,
        cur,
        *,
        selected: list[tuple],
        lease_token: str,
        lease_expires_at: int,
        now: int,
    ) -> None:
        """Move selected frontier rows into leased state."""
        if not selected:
            return
        ph = sql_placeholder()
        selected_hashes = [row[0] for row in selected]
        cur.execute(
            f"""
            UPDATE frontier_entries
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

    def _lease_frontier_candidates(
        self,
        cur,
        *,
        now: int,
        count: int,
        max_per_domain: int,
        lease_token: str,
        lease_expires_at: int,
        crawl_profiles: tuple[str, ...] | None = None,
    ) -> list[tuple]:
        """Select and lease a bounded candidate set for the given profile slice."""
        if count <= 0:
            return []

        overscan = max(count * max_per_domain * 6, count * 2)
        candidates = self._select_ready_frontier_candidates(
            cur,
            now=now,
            overscan=overscan,
            max_per_domain=max_per_domain,
            crawl_profiles=crawl_profiles,
        )
        selected = self._choose_frontier_candidates(
            candidates,
            now=now,
            count=count,
            max_per_domain=max_per_domain,
        )
        if selected:
            self._mark_frontier_entries_leased(
                cur,
                selected=selected,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                now=now,
            )
        return selected

    def _promote_manual_frontier_lease(
        self,
        cur,
        *,
        url_hash_value: str,
        lease_token: str,
        lease_expires_at: int,
        now: int,
    ) -> str | None:
        """Promote a frontier row into a manual lease and return its domain."""
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT domain, status, lease_expires_at
            FROM frontier_entries
            WHERE url_hash = {ph}
            FOR UPDATE
            """,
            (url_hash_value,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        domain, status, existing_lease_expires_at = row
        if status == "leased" and (
            existing_lease_expires_at is None or existing_lease_expires_at > now
        ):
            return None

        cur.execute(
            f"""
            UPDATE frontier_entries
            SET
                discovered_via = 'manual',
                crawl_profile = 'manual_now',
                priority_bucket = 0,
                priority_score = GREATEST(priority_score, {ph}),
                status = 'leased',
                next_fetch_at = LEAST(next_fetch_at, {ph}),
                lease_token = {ph},
                lease_expires_at = {ph},
                updated_at = {ph}
            WHERE url_hash = {ph}
            """,
            (
                POLICIES["manual_now"].priority_score_boost,
                now,
                lease_token,
                lease_expires_at,
                now,
                url_hash_value,
            ),
        )
        if hasattr(self, "domain_scheduling_state"):
            self.domain_scheduling_state.adjust_inflight_leases(
                cur, [domain], delta=1, now=now
            )
        return domain

    def _update_frontier_entry_after_result(
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
        """Persist the frontier row transition after a crawl attempt."""
        ph = sql_placeholder()
        cur.execute(
            f"""
            UPDATE frontier_entries
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

    def reconcile_expired_frontier_leases(self) -> int:
        """Return expired leased frontier entries back to pending."""
        now = int(time.time())
        with db_transaction(self.db_path) as cur:
            return self._reconcile_expired_frontier_leases(cur, now=now)

    def pop_frontier_batch(
        self,
        count: int,
        *,
        max_per_domain: int = 3,
        lease_seconds: int = 300,
    ) -> list[UrlItem]:
        """Lease ready frontier entries with basic domain diversity."""
        if count <= 0:
            return []
        now = int(time.time())
        lease_token = uuid.uuid4().hex
        lease_expires_at = now + max(1, lease_seconds)
        selected: list[tuple] = []
        for attempt in range(_FRONTIER_RETRY_LIMIT + 1):
            try:
                selected = []
                with db_transaction(self.db_path) as cur:
                    self._reconcile_expired_frontier_leases(cur, now=now)
                    for tier_budget in allocate_frontier_tier_budgets(count):
                        remaining = count - len(selected)
                        if remaining <= 0:
                            break
                        selected.extend(
                            self._lease_frontier_candidates(
                                cur,
                                now=now,
                                count=min(tier_budget.leases, remaining),
                                max_per_domain=max_per_domain,
                                lease_token=lease_token,
                                lease_expires_at=lease_expires_at,
                                crawl_profiles=tier_budget.profiles,
                            )
                        )

                    remaining = count - len(selected)
                    if remaining > 0:
                        selected.extend(
                            self._lease_frontier_candidates(
                                cur,
                                now=now,
                                count=remaining,
                                max_per_domain=max_per_domain,
                                lease_token=lease_token,
                                lease_expires_at=lease_expires_at,
                            )
                        )
                break
            except (DeadlockDetected, SerializationFailure):
                if attempt >= _FRONTIER_RETRY_LIMIT:
                    raise
                time.sleep(_FRONTIER_RETRY_BASE_SEC * (attempt + 1))

        if not selected:
            return []

        return [
            UrlItem(url=row[1], domain=row[2], created_at=row[3]) for row in selected
        ]

    def lease_manual_url(self, url: str, *, lease_seconds: int = 300) -> bool:
        """Lease a single URL for immediate operator-triggered crawl."""
        self.discover_and_admit_urls([url], discovered_via="manual")

        now = int(time.time())
        lease_token = uuid.uuid4().hex
        lease_expires_at = now + max(1, lease_seconds)
        h = url_hash(url)
        with db_transaction(self.db_path) as cur:
            self._reconcile_expired_frontier_leases(cur, now=now)
            domain = self._promote_manual_frontier_lease(
                cur,
                url_hash_value=h,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
                now=now,
            )
            if domain is None:
                return False
            return True

    def release_frontier_urls(
        self,
        urls: list[str],
        *,
        delay_seconds: int = 0,
        prefer_earlier: bool = False,
    ) -> int:
        """Release leased frontier entries back to pending."""
        if not urls:
            return 0
        now = int(time.time())
        next_fetch_at = now + max(0, delay_seconds)
        hashes = [url_hash(url) for url in urls]
        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT domain
                FROM frontier_entries
                WHERE url_hash = ANY({sql_placeholder()})
                  AND status = 'leased'
                """,
                (hashes,),
            )
            leased_domains = [row[0] for row in cur.fetchall()]
            cur.execute(
                f"""
                UPDATE frontier_entries
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

    def record_frontier_result(self, url: str, status: str) -> None:
        """Persist frontier completion state and next eligible fetch time."""
        now = int(time.time())
        h = url_hash(url)
        is_success = status == "done"

        with db_transaction(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT
                    url,
                    domain,
                    crawl_profile,
                    fail_streak,
                    status,
                    is_seed,
                    canonical_source
                FROM frontier_entries
                WHERE url_hash = {sql_placeholder()}
                """,
                (h,),
            )
            row = cur.fetchone()
            if row is None:
                return

            url = row[0]
            domain = row[1]
            crawl_profile = row[2] or "generic"
            fail_streak = int(row[3] or 0)
            was_leased = row[4] == "leased"
            is_seed = bool(row[5])
            canonical_source = row[6]
            priority_bucket: int | None = None
            priority_score: float | None = None

            if is_success and crawl_profile == "manual_now":
                reassigned = assign_crawl_policy(
                    url,
                    discovered_via="seed" if is_seed else "outlink",
                    is_seed=is_seed,
                )
                crawl_profile = reassigned.crawl_profile
                canonical_source = reassigned.canonical_source
                priority_bucket = reassigned.priority_bucket
                priority_score = reassigned.priority_score

            policy = POLICIES.get(crawl_profile, POLICIES["generic"])

            if is_success:
                next_delay = compute_success_recrawl_delay(
                    crawl_profile,
                    is_seed=is_seed,
                    canonical_source=canonical_source,
                )
                next_fail_streak = 0
                last_success_at = now
            else:
                next_delay = max(
                    compute_failure_retry_delay(
                        crawl_profile,
                        fail_streak=fail_streak,
                    ),
                    int(max(policy.host_min_interval_sec, 1.0)),
                )
                next_fail_streak = fail_streak + 1
                last_success_at = None

            self._update_frontier_entry_after_result(
                cur,
                url_hash_value=h,
                status=status,
                next_fetch_at=now + next_delay,
                last_fetched_at=now,
                last_success_at=last_success_at,
                next_fail_streak=next_fail_streak,
                now=now,
            )
            if priority_bucket is not None and priority_score is not None:
                cur.execute(
                    f"""
                    UPDATE frontier_entries
                    SET
                        crawl_profile = {sql_placeholder()},
                        canonical_source = {sql_placeholder()},
                        priority_bucket = {sql_placeholder()},
                        priority_score = {sql_placeholder()},
                        updated_at = {sql_placeholder()}
                    WHERE url_hash = {sql_placeholder()}
                    """,
                    (
                        crawl_profile,
                        canonical_source,
                        priority_bucket,
                        priority_score,
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
                    policy=policy,
                    is_success=is_success,
                    now=now,
                )
