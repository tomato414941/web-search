"""Shared crawler runtime helpers."""

from web_search_crawler.core.config import settings
from web_search_crawler.core.crawl_denylist import load_crawl_denylist
from web_search_crawler.core.url_filters import UrlFilter, load_url_filters
from web_search_crawler.db.url_store import UrlStore
from web_search_crawler.frontier_planner import FrontierPlanner, FrontierPlannerConfig


def build_frontier_planner(url_store: UrlStore, *, batch_size: int) -> FrontierPlanner:
    return FrontierPlanner(
        url_store,
        FrontierPlannerConfig(
            domain_max_concurrent=settings.FRONTIER_PLANNER_DOMAIN_MAX_CONCURRENT,
            batch_size=batch_size,
            lease_seconds=settings.FRONTIER_PLANNER_LEASE_SECONDS,
        ),
    )


def load_static_crawl_config(
    planner: FrontierPlanner,
) -> tuple[frozenset[str], UrlFilter]:
    blocked_domains = load_crawl_denylist(settings.CRAWL_DENYLIST_PATH)
    planner.set_denied_domains(blocked_domains)
    url_filter = load_url_filters(settings.URL_FILTERS_PATH)
    return blocked_domains, url_filter
