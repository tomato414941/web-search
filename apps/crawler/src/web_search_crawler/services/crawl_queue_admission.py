"""Discovered URL filtering and crawl queue admission."""

import logging
import random
from typing import Literal
from urllib.parse import urlparse

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.db.executor import run_in_db_executor
from web_search_core.urls import get_domain
from web_search_crawler.workers.types import PipelineContext
from web_search_core.utils import MAX_URL_LENGTH

logger = logging.getLogger(__name__)

DiscoveryKind = Literal["html_outlink", "syndication_feed"]


def should_enqueue_discovered_url(
    url: str,
    *,
    source_url: str,
    discovery_kind: DiscoveryKind,
) -> bool:
    """Return whether a discovered URL should become a crawl task."""
    if discovery_kind == "syndication_feed":
        return True

    parsed = urlparse(url)
    if parsed.query or parsed.fragment or "*" in parsed.path:
        return False

    return get_domain(url) == get_domain(source_url)


def select_urls_to_enqueue(
    urls: list[str],
    *,
    discovery_kind: DiscoveryKind,
) -> list[str]:
    """Limit HTML outlink expansion while preserving feed discovery."""
    if discovery_kind == "syndication_feed":
        return urls
    if not urls:
        return []
    return [random.choice(urls)]


async def admit_discovered_urls(
    ctx: PipelineContext,
    discovered: list[str],
    *,
    discovery_kind: DiscoveryKind = "html_outlink",
) -> None:
    """Record discovered URLs and enqueue only high-value crawl candidates."""
    if not discovered:
        return

    valid_urls = [
        u
        for u in discovered
        if len(u) <= MAX_URL_LENGTH
        and not is_domain_denied(get_domain(u), ctx.blocked_domains)
        and not (ctx.url_filter and ctx.url_filter.is_filtered(u))
    ]

    if valid_urls:
        await run_in_db_executor(
            ctx.url_ledger.record_discovered_urls,
            valid_urls,
        )
        queueable_urls = [
            u
            for u in valid_urls
            if should_enqueue_discovered_url(
                u,
                source_url=ctx.url,
                discovery_kind=discovery_kind,
            )
        ]
        queueable_urls = select_urls_to_enqueue(
            queueable_urls,
            discovery_kind=discovery_kind,
        )
        if queueable_urls:
            await run_in_db_executor(
                ctx.url_store.enqueue_urls_for_crawl,
                queueable_urls,
            )
    logger.debug(
        "Admitted discovered URLs from %s with %s kind (%d discovered)",
        ctx.url,
        discovery_kind,
        len(discovered),
    )
