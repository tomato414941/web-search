"""Shared types for crawler processing stages."""

from dataclasses import dataclass, field
from typing import Literal

import aiohttp

from web_search_crawler.core.url_filters import UrlFilter
from web_search_crawler.db.crawler_runtime_store import CrawlerRuntimeStore
from web_search_crawler.crawl_task_planner import CrawlTaskPlanner
from web_search_crawler.services.fetchers import AiohttpFetcher, Fetcher
from web_search_crawler.utils.robots import AsyncRobotsCache
from web_search_core.urls import get_domain
from web_search_web_model import LinkGraphRepository, UrlLedgerRepository


@dataclass
class PipelineContext:
    """Shared state passed through crawler processing stages."""

    session: aiohttp.ClientSession
    robots: AsyncRobotsCache
    url_store: CrawlerRuntimeStore
    url_ledger: UrlLedgerRepository
    link_graph: LinkGraphRepository
    planner: CrawlTaskPlanner
    url: str
    domain: str = field(init=False)
    blocked_domains: frozenset[str] = field(default_factory=frozenset)
    url_filter: UrlFilter | None = None
    domain_cache: dict = field(default_factory=dict)
    indexer_session: aiohttp.ClientSession | None = None
    fetcher: Fetcher = field(default_factory=AiohttpFetcher)

    def __post_init__(self) -> None:
        self.domain = get_domain(self.url)


@dataclass
class ParseResult:
    """Result of HTML parsing."""

    title: str
    content: str
    outlinks: list[str]
    feed_links: list[str]
    published_at: str | None = None
    updated_at: str | None = None
    author: str | None = None
    organization: str | None = None


@dataclass
class CrawlStageTimings:
    """Per-stage timings for one crawl attempt."""

    precheck_ms: int | None = None
    robots_ms: int | None = None
    ssrf_ms: int | None = None
    crawl_delay_ms: int | None = None
    fetch_ms: int | None = None
    fetch_request_ms: int | None = None
    fetch_body_read_ms: int | None = None
    parse_ms: int | None = None
    submit_ms: int | None = None
    total_ms: int | None = None


@dataclass(frozen=True)
class PipelineProcessResult:
    """Normalized outcome for post-fetch crawl processing."""

    status: Literal["queued_for_index", "skipped", "failed", "retry"]
    message: str
    job_id: str | None = None
    outlinks_discovered: int = 0
    host_error: bool = False
    timings: CrawlStageTimings | None = None
