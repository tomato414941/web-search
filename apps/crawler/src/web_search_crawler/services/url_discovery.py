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
    admission_intent: str = "normal",
    discovery_depth: int = 1,
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
            ctx.url_ledger.record_discovered_urls,
            valid_urls,
        )
        await run_in_db_executor(
            ctx.url_store.admit_urls_to_frontier,
            valid_urls,
            admission_intent=admission_intent,
            discovery_depth=discovery_depth,
        )
    logger.debug(
        "Admitted discovered URLs from %s with %s intent (%d discovered)",
        ctx.url,
        admission_intent,
        len(discovered),
    )
