"""Durable per-domain crawl planning state."""

from __future__ import annotations

import time
from collections import Counter

from psycopg2.extras import execute_values

from web_search_crawler.db.connection import db_connection, db_transaction
from web_search_crawler.db.url_types import DomainState
from web_search_postgres.search import sql_placeholder

MAX_DOMAIN_BACKOFF_SEC = 3600


class DomainSchedulingStateStore:
    """Persistent host-level crawl state."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def ensure_domain_state_rows(
        self,
        cur,
        domains: list[str],
        *,
        now: int,
        default_crawl_delay_sec: float = 1.0,
    ) -> None:
        unique_domains = sorted({domain for domain in domains if domain})
        if not unique_domains:
            return
        execute_values(
            cur,
            """
            INSERT INTO domain_state (
                domain,
                next_request_at,
                crawl_delay_sec,
                backoff_until,
                fail_streak,
                inflight_leases,
                updated_at
            )
            VALUES %s
            ON CONFLICT (domain) DO NOTHING
            """,
            [
                (
                    domain,
                    0,
                    default_crawl_delay_sec,
                    None,
                    0,
                    0,
                    now,
                )
                for domain in unique_domains
            ],
        )

    def reconcile_inflight_leases(self, cur, *, now: int) -> int:
        """Repair drift between domain_state.inflight_leases and crawl task leases."""
        ph = sql_placeholder()
        cur.execute(
            f"""
            INSERT INTO domain_state (
                domain,
                next_request_at,
                crawl_delay_sec,
                backoff_until,
                fail_streak,
                inflight_leases,
                updated_at
            )
            SELECT
                frontier.domain,
                0,
                1.0,
                NULL,
                0,
                frontier.leased,
                {ph}
            FROM (
                SELECT domain, COUNT(*)::INTEGER AS leased
                FROM crawl_schedule
                WHERE status = 'leased'
                GROUP BY domain
            ) AS frontier
            LEFT JOIN domain_state AS ds ON ds.domain = frontier.domain
            WHERE ds.domain IS NULL
            """,
            (now,),
        )
        inserted = cur.rowcount
        cur.execute(
            f"""
            WITH actual AS (
                SELECT domain, COUNT(*)::INTEGER AS leased
                FROM crawl_schedule
                WHERE status = 'leased'
                GROUP BY domain
            )
            UPDATE domain_state AS ds
            SET
                inflight_leases = actual.leased,
                updated_at = {ph}
            FROM actual
            WHERE ds.domain = actual.domain
              AND ds.inflight_leases <> actual.leased
            """,
            (now,),
        )
        updated = cur.rowcount
        cur.execute(
            f"""
            UPDATE domain_state AS ds
            SET
                inflight_leases = 0,
                updated_at = {ph}
            WHERE ds.inflight_leases <> 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM crawl_schedule AS frontier
                  WHERE frontier.domain = ds.domain
                    AND frontier.status = 'leased'
              )
            """,
            (now,),
        )
        cleared = cur.rowcount
        return inserted + updated + cleared

    def ensure_missing_domain_state_rows(
        self,
        cur,
        domains: list[str],
        *,
        now: int,
        default_crawl_delay_sec: float = 1.0,
    ) -> None:
        unique_domains = sorted({domain for domain in domains if domain})
        if not unique_domains:
            return
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT requested.domain
            FROM UNNEST({ph}::text[]) AS requested(domain)
            LEFT JOIN domain_state AS ds ON ds.domain = requested.domain
            WHERE ds.domain IS NULL
            """,
            (unique_domains,),
        )
        missing = [row[0] for row in cur.fetchall()]
        if not missing:
            return
        self.ensure_domain_state_rows(
            cur,
            missing,
            now=now,
            default_crawl_delay_sec=default_crawl_delay_sec,
        )

    def adjust_inflight_leases(
        self,
        cur,
        domains: list[str],
        *,
        delta: int,
        now: int,
    ) -> None:
        if not domains:
            return
        counts = Counter(domains)
        execute_values(
            cur,
            """
            UPDATE domain_state AS ds
            SET
                inflight_leases = GREATEST(ds.inflight_leases + delta.delta, 0),
                updated_at = delta.updated_at
            FROM (VALUES %s) AS delta(domain, delta, updated_at)
            WHERE ds.domain = delta.domain
            """,
            [(domain, count * delta, now) for domain, count in sorted(counts.items())],
            template="(%s, %s, %s)",
        )
        if cur.rowcount < len(counts):
            self.ensure_missing_domain_state_rows(cur, domains, now=now)
            execute_values(
                cur,
                """
                UPDATE domain_state AS ds
                SET
                    inflight_leases = GREATEST(ds.inflight_leases + delta.delta, 0),
                    updated_at = delta.updated_at
                FROM (VALUES %s) AS delta(domain, delta, updated_at)
                WHERE ds.domain = delta.domain
                """,
                [
                    (domain, count * delta, now)
                    for domain, count in sorted(counts.items())
                ],
                template="(%s, %s, %s)",
            )

    def get_domain_state(self, domain: str) -> DomainState | None:
        """Return persistent planning state for a domain, if present."""
        ph = sql_placeholder()
        with db_connection(self.db_path) as cur:
            cur.execute(
                f"""
                SELECT
                    domain,
                    next_request_at,
                    crawl_delay_sec,
                    backoff_until,
                    fail_streak,
                    inflight_leases
                FROM domain_state
                WHERE domain = {ph}
                """,
                (domain,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return DomainState(
                domain=row[0],
                next_request_at=row[1],
                crawl_delay_sec=float(row[2]),
                backoff_until=row[3],
                fail_streak=row[4],
                inflight_leases=row[5],
            )

    def set_domain_crawl_delay(self, domain: str, delay: float) -> None:
        """Persist robots-derived crawl delay for a domain."""
        if not domain:
            return
        now = int(time.time())
        normalized_delay = max(float(delay), 0.0)
        ph = sql_placeholder()
        with db_transaction(self.db_path) as cur:
            self.ensure_domain_state_rows(cur, [domain], now=now)
            cur.execute(
                f"""
                UPDATE domain_state
                SET
                    crawl_delay_sec = GREATEST(crawl_delay_sec, {ph}),
                    updated_at = {ph}
                WHERE domain = {ph}
                """,
                (normalized_delay, now, domain),
            )

    def record_domain_retry(self, domain: str, *, default_delay_sec: float) -> None:
        """Apply exponential backoff after a retryable host error."""
        if not domain:
            return
        now = int(time.time())
        ph = sql_placeholder()
        with db_transaction(self.db_path) as cur:
            self.ensure_domain_state_rows(
                cur,
                [domain],
                now=now,
                default_crawl_delay_sec=default_delay_sec,
            )
            cur.execute(
                f"""
                UPDATE domain_state
                SET
                    fail_streak = fail_streak + 1,
                    backoff_until = {ph} + LEAST(
                        GREATEST(CEIL(crawl_delay_sec)::INTEGER, 1)
                        * (2 ^ LEAST(fail_streak + 1, 10)),
                        {ph}
                    ),
                    updated_at = {ph}
                WHERE domain = {ph}
                """,
                (now, MAX_DOMAIN_BACKOFF_SEC, now, domain),
            )

    def record_crawl_result(
        self,
        cur,
        *,
        domain: str,
        is_success: bool,
        now: int,
    ) -> None:
        """Persist domain-level scheduling state after a crawl attempt."""
        if not domain:
            return
        ph = sql_placeholder()
        if is_success:
            cur.execute(
                f"""
                UPDATE domain_state
                SET
                    next_request_at = {ph} + GREATEST(CEIL(crawl_delay_sec)::INTEGER, 1),
                    backoff_until = NULL,
                    fail_streak = 0,
                    updated_at = {ph}
                WHERE domain = {ph}
                """,
                (now, now, domain),
            )
            if cur.rowcount == 0:
                self.ensure_missing_domain_state_rows(
                    cur,
                    [domain],
                    now=now,
                )
                cur.execute(
                    f"""
                    UPDATE domain_state
                    SET
                        next_request_at = {ph} + GREATEST(CEIL(crawl_delay_sec)::INTEGER, 1),
                        backoff_until = NULL,
                        fail_streak = 0,
                        updated_at = {ph}
                    WHERE domain = {ph}
                    """,
                    (now, now, domain),
                )
            return

        cur.execute(
            f"""
            UPDATE domain_state
            SET
                fail_streak = fail_streak + 1,
                backoff_until = {ph} + LEAST(
                    GREATEST(CEIL(crawl_delay_sec)::INTEGER, 1)
                    * (2 ^ LEAST(fail_streak + 1, 10)),
                    {ph}
                ),
                updated_at = {ph}
            WHERE domain = {ph}
            """,
            (now, MAX_DOMAIN_BACKOFF_SEC, now, domain),
        )
        if cur.rowcount == 0:
            self.ensure_missing_domain_state_rows(
                cur,
                [domain],
                now=now,
            )
            cur.execute(
                f"""
                UPDATE domain_state
                SET
                    fail_streak = fail_streak + 1,
                    backoff_until = {ph} + LEAST(
                        GREATEST(CEIL(crawl_delay_sec)::INTEGER, 1)
                        * (2 ^ LEAST(fail_streak + 1, 10)),
                        {ph}
                    ),
                    updated_at = {ph}
                WHERE domain = {ph}
                """,
                (now, MAX_DOMAIN_BACKOFF_SEC, now, domain),
            )
