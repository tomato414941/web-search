"""Discovered URL filtering and frontier admission."""

import logging

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.db.url_types import get_domain
from web_search_crawler.workers.types import PipelineContext
from web_search_core.utils import MAX_URL_LENGTH

logger = logging.getLogger(__name__)


async def admit_discovered_urls(
    ctx: PipelineContext,
    discovered: list[str],
    *,
    discovered_via: str = "outlink",
) -> None:
    """Filter and admit discovered URLs into the crawl frontier."""
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
            ctx.url_store.discover_and_admit_urls,
            valid_urls,
            discovered_via=discovered_via,
        )
    logger.debug(
        "Admitted discovered URLs from %s via %s (%d discovered)",
        ctx.url,
        discovered_via,
        len(discovered),
    )
