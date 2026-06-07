"""Crawler runtime store for crawl scheduling state."""

import time

from web_search_crawler.core.config import settings
from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.crawl_schedule_admission import CrawlScheduleAdmissionMixin
from web_search_crawler.db.url_domain_state import DomainSchedulingStateStore
from web_search_crawler.db.crawl_schedule import CrawlScheduleMixin
from web_search_crawler.db.url_queries import UrlQueriesMixin
from web_search_crawler.db.url_retry import UrlRetryMixin
from web_search_crawler.db.url_maintenance import UrlMaintenanceMixin
from web_search_core.url_admission import (
    URLAdmissionPolicy,
    load_url_admission_policy,
)
from web_search_postgres.search import get_connection


class CrawlerRuntimeStore(
    CrawlScheduleAdmissionMixin,
    CrawlScheduleMixin,
    UrlRetryMixin,
    UrlQueriesMixin,
    UrlMaintenanceMixin,
):
    """
    Crawler runtime storage backed by a durable crawl schedule.

    crawl_schedule: database table for scheduled crawl tasks.
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
        self.domain_scheduling_state = DomainSchedulingStateStore(db_path)
        self._init_db()

    def _init_db(self):
        # Schema is managed by Alembic; verify connectivity and bootstrap runtime rows.
        con = get_connection()
        con.close()
        self._bootstrap_runtime_state()

    def _bootstrap_runtime_state(self) -> None:
        now = int(time.time())
        with db_transaction(self.db_path) as cur:
            self.domain_scheduling_state.reconcile_inflight_leases(cur, now=now)

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
