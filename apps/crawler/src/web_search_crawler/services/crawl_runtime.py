"""Shared crawler runtime helpers."""

from web_search_crawler.core.config import settings
from web_search_crawler.core.crawl_denylist import load_crawl_denylist
from web_search_crawler.core.url_filters import UrlFilter, load_url_filters
from web_search_crawler.db.crawler_runtime_store import CrawlerRuntimeStore
from web_search_crawler.crawl_task_planner import (
    CrawlTaskPlanner,
    CrawlTaskPlannerConfig,
)
from web_search_core.url_admission import load_url_admission_policy
from web_search_postgres.repositories import UrlLedgerRepository


def build_crawler_runtime_store() -> CrawlerRuntimeStore:
    return CrawlerRuntimeStore(
        settings.CRAWLER_DB_PATH,
        recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
    )


def build_url_ledger_repository() -> UrlLedgerRepository:
    return UrlLedgerRepository(
        load_url_admission_policy(settings.URL_ADMISSION_RULES_PATH),
    )


def build_crawl_task_planner(
    url_store: CrawlerRuntimeStore, *, batch_size: int
) -> CrawlTaskPlanner:
    return CrawlTaskPlanner(
        url_store,
        CrawlTaskPlannerConfig(
            domain_max_concurrent=settings.CRAWL_TASK_PLANNER_DOMAIN_MAX_CONCURRENT,
            batch_size=batch_size,
            lease_seconds=settings.CRAWL_TASK_PLANNER_LEASE_SECONDS,
        ),
    )


def load_static_crawl_config(
    planner: CrawlTaskPlanner,
) -> tuple[frozenset[str], UrlFilter]:
    blocked_domains = load_crawl_denylist(settings.CRAWL_DENYLIST_PATH)
    planner.set_denied_domains(blocked_domains)
    url_filter = load_url_filters(settings.URL_FILTERS_PATH)
    return blocked_domains, url_filter
