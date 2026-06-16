"""Discovered URL filtering and crawl schedule admission."""

import logging
from typing import Literal
from urllib.parse import urlparse

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.db.executor import run_in_db_executor
from web_search_core.urls import get_domain
from web_search_crawler.workers.types import PipelineContext
from web_search_core.utils import MAX_URL_LENGTH

logger = logging.getLogger(__name__)

DiscoveryKind = Literal["html_outlink", "syndication_feed"]

_SCHEDULABLE_HUB_SEGMENTS = frozenset(
    {
        "announcements",
        "api",
        "blog",
        "blogs",
        "changelog",
        "docs",
        "documentation",
        "news",
        "reference",
        "release",
        "releases",
        "release-notes",
        "whatsnew",
    }
)
_UNSCHEDULABLE_SEGMENTS = frozenset(
    {
        "account",
        "admin",
        "cart",
        "edit",
        "filter",
        "login",
        "logout",
        "my",
        "search",
        "signin",
        "signup",
        "sort",
        "tag",
        "tags",
    }
)


def _path_segments(url: str) -> tuple[str, ...]:
    parsed = urlparse(url)
    return tuple(segment.lower() for segment in parsed.path.split("/") if segment)


def should_schedule_discovered_url(
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

    if get_domain(url) != get_domain(source_url):
        return False

    segments = _path_segments(url)
    if not segments or len(segments) > 2:
        return False
    if any(segment in _UNSCHEDULABLE_SEGMENTS for segment in segments):
        return False
    return any(segment in _SCHEDULABLE_HUB_SEGMENTS for segment in segments)


async def admit_discovered_urls(
    ctx: PipelineContext,
    discovered: list[str],
    *,
    admission_intent: str = "normal",
    discovery_kind: DiscoveryKind = "html_outlink",
) -> None:
    """Record discovered URLs and schedule only high-value crawl candidates."""
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
        schedulable_urls = [
            u
            for u in valid_urls
            if should_schedule_discovered_url(
                u,
                source_url=ctx.url,
                discovery_kind=discovery_kind,
            )
        ]
        if schedulable_urls:
            await run_in_db_executor(
                ctx.url_store.schedule_urls_for_crawl,
                schedulable_urls,
                admission_intent=admission_intent,
            )
    logger.debug(
        "Admitted discovered URLs from %s with %s intent and %s kind (%d discovered)",
        ctx.url,
        admission_intent,
        discovery_kind,
        len(discovered),
    )
