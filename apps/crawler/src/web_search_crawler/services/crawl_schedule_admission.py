"""Discovered URL filtering and crawl schedule admission."""

import logging

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.db.executor import run_in_db_executor
from web_search_core.urls import get_domain
from web_search_crawler.workers.types import PipelineContext
from web_search_core.utils import MAX_URL_LENGTH

logger = logging.getLogger(__name__)


async def admit_discovered_urls(
    ctx: PipelineContext,
    discovered: list[str],
    *,
    admission_intent: str = "normal",
) -> None:
    """Filter discovered URLs and schedule them for crawling."""
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
            ctx.url_store.schedule_urls_for_crawl,
            valid_urls,
            admission_intent=admission_intent,
        )
    logger.debug(
        "Admitted discovered URLs from %s with %s intent (%d discovered)",
        ctx.url,
        admission_intent,
        len(discovered),
    )
