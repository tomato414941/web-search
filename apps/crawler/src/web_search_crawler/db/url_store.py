"""
URL Store - Discovery Ledger + Frontier

urls table: ledger of all discovered URLs and their discovery route.
frontier_entries table: durable crawl frontier.
"""

import os
import time

from web_search_crawler.core.config import settings
from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_admin_state import FrontierAdminStateStore
from web_search_crawler.db.url_discovery import UrlDiscoveryMixin
from web_search_crawler.db.url_domain_state import DomainSchedulingStateStore
from web_search_crawler.db.url_frontier import UrlFrontierMixin
from web_search_crawler.db.url_queries import UrlQueriesMixin
from web_search_crawler.db.url_retry import UrlRetryMixin
from web_search_crawler.db.url_seeds import UrlSeedsMixin
from web_search_crawler.services.url_admission import (
    URLAdmissionPolicy,
    load_url_admission_policy,
)
from web_search_core.infrastructure_config import Environment
from web_search_postgres.search import get_connection


class UrlStore(
    UrlDiscoveryMixin,
    UrlFrontierMixin,
    UrlRetryMixin,
    UrlQueriesMixin,
    UrlSeedsMixin,
):
    """
    URL storage backed by a discovery ledger and durable frontier.

    urls: all discovered URLs. last_crawled_at IS NULL means never crawled.
    frontier_entries: active pending/leased crawl candidates.
    """

    def __init__(
        self,
        db_path: str,
        recrawl_after_days: int = 30,
    ):
        self.db_path = db_path
        self.recrawl_threshold = recrawl_after_days * 86400
        self.url_admission_policy: URLAdmissionPolicy = load_url_admission_policy(
            settings.URL_ADMISSION_RULES_PATH
        )
        counter_refresh_sec = settings.ADMIN_CACHE_REFRESH_SEC
        if settings.ENVIRONMENT == Environment.TEST:
            counter_refresh_sec = 0
        self.frontier_admin_state = FrontierAdminStateStore(
            db_path,
            refresh_interval_sec=counter_refresh_sec,
        )
        self.domain_scheduling_state = DomainSchedulingStateStore(db_path)
        self._stats_cache_ttl_sec = int(os.getenv("CRAWL_STATS_CACHE_TTL_SEC", "15"))
        self._stats_cache: tuple[dict[str, int], float] | None = None
        self._init_db()

    def _init_db(self):
        # Schema is managed by Alembic; verify connectivity and bootstrap runtime rows.
        con = get_connection()
        con.close()
        self._bootstrap_runtime_state()

    def _bootstrap_runtime_state(self) -> None:
        now = int(time.time())
        with db_transaction(self.db_path) as cur:
            self.frontier_admin_state.ensure_frontier_counters_row(cur, now=now)
            self.frontier_admin_state.ensure_frontier_snapshot_row(cur, now=now)
            self.domain_scheduling_state.reconcile_inflight_leases(cur, now=now)
        if self.frontier_admin_state._refresh_interval_sec == 0:
            self.frontier_admin_state.rebuild_frontier_counters(now=now)

    def _get_cached_stats(self) -> dict[str, int] | None:
        if self._stats_cache is None:
            return None
        stats, cached_at = self._stats_cache
        if time.time() - cached_at >= self._stats_cache_ttl_sec:
            self._stats_cache = None
            return None
        return stats.copy()

    def _set_cached_stats(self, stats: dict[str, int]) -> None:
        self._stats_cache = (stats.copy(), time.time())

    def _drop_cached_stats(self) -> None:
        self._stats_cache = None

    def get_frontier_counters(self) -> dict[str, int]:
        return self.frontier_admin_state.get_frontier_counters()

    def set_frontier_counters(
        self,
        *,
        pending_rows: int,
        leased_rows: int,
        frontier_rows: int,
        now: int | None = None,
    ) -> dict[str, int]:
        return self.frontier_admin_state.set_frontier_counters(
            pending_rows=pending_rows,
            leased_rows=leased_rows,
            frontier_rows=frontier_rows,
            now=now,
        )

    def rebuild_frontier_counters(self, *, now: int | None = None) -> dict[str, int]:
        return self.frontier_admin_state.rebuild_frontier_counters(now=now)

    def write_frontier_snapshot(
        self,
        snapshot: dict,
        *,
        generated_at: int | None = None,
        last_error: str | None = None,
    ) -> dict:
        return self.frontier_admin_state.write_frontier_snapshot(
            snapshot,
            generated_at=generated_at,
            last_error=last_error,
        )

    def record_frontier_snapshot_error(self, last_error: str) -> None:
        self.frontier_admin_state.record_frontier_snapshot_error(last_error)

    def get_frontier_snapshot_record(self) -> dict:
        return self.frontier_admin_state.get_frontier_snapshot_record()

    def get_frontier_snapshot_payload(
        self,
        *,
        snapshot_ttl_sec: int,
        empty_snapshot: dict,
        now: int | None = None,
    ) -> dict:
        return self.frontier_admin_state.get_frontier_snapshot_payload(
            snapshot_ttl_sec=snapshot_ttl_sec,
            empty_snapshot=empty_snapshot,
            now=now,
        )

    def get_frontier_dashboard_summary(
        self,
        *,
        snapshot_ttl_sec: int,
        now: int | None = None,
    ) -> dict[str, int | bool]:
        return self.frontier_admin_state.get_frontier_dashboard_summary(
            snapshot_ttl_sec=snapshot_ttl_sec,
            now=now,
        )

    def get_domain_state(self, domain: str):
        return self.domain_scheduling_state.get_domain_state(domain)

    def set_domain_crawl_delay(self, domain: str, delay: float) -> None:
        self.domain_scheduling_state.set_domain_crawl_delay(domain, delay)

    def record_domain_retry(self, domain: str, *, default_delay_sec: float) -> None:
        self.domain_scheduling_state.record_domain_retry(
            domain,
            default_delay_sec=default_delay_sec,
        )

    def reconcile_domain_state_inflight_leases(self) -> int:
        now = int(time.time())
        with db_transaction(self.db_path) as cur:
            return self.domain_scheduling_state.reconcile_inflight_leases(cur, now=now)
