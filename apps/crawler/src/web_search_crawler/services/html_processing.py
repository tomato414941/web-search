"""HTML page processing for crawler fetch results."""

import asyncio
import time

from web_search_crawler.core.config import settings
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.services.indexer import (
    IndexerSubmitResult,
    submit_page_to_indexer,
)
from web_search_crawler.services.crawl_schedule_admission import admit_discovered_urls
from web_search_crawler.utils import history as history_log
from web_search_crawler.utils.parser import parse_page
from web_search_crawler.workers.timing import elapsed_ms, timing_kwargs
from web_search_crawler.workers.types import (
    CrawlStageTimings,
    ParseResult,
    PipelineContext,
    PipelineProcessResult,
)
from web_search_contracts.enums import CrawlAttemptStatus, CrawlUrlStatus


async def parse_html_page(html: str, url: str, max_outlinks: int) -> ParseResult:
    """Parse HTML into title, main content, metadata, and discovered links."""
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, parse_page, html, url, max_outlinks)
    return ParseResult(
        title=doc.title,
        content=doc.content,
        outlinks=doc.outlinks or [],
        feed_links=doc.feed_links or [],
        published_at=doc.published_at,
        updated_at=doc.updated_at,
        author=doc.author,
        organization=doc.organization,
    )


async def submit_html_page_to_indexer(
    ctx: PipelineContext, parsed: ParseResult
) -> IndexerSubmitResult:
    """Submit parsed HTML page content to the indexer API."""
    return await submit_page_to_indexer(
        ctx.indexer_session or ctx.session,
        settings.INDEXER_API_URL,
        settings.INDEXER_API_KEY,
        ctx.url,
        parsed.title,
        parsed.content,
        outlinks=parsed.outlinks,
        published_at=parsed.published_at,
        updated_at=parsed.updated_at,
        author=parsed.author,
        organization=parsed.organization,
    )


async def process_html_result(
    ctx: PipelineContext,
    html: str,
    *,
    max_outlinks: int,
    timings: CrawlStageTimings,
    total_started_at: float,
) -> PipelineProcessResult:
    parse_started_at = time.perf_counter()
    parsed = await parse_html_page(html, ctx.url, max_outlinks)
    timings.parse_ms = elapsed_ms(parse_started_at)

    outlinks_discovered = len(parsed.outlinks)
    if parsed.feed_links:
        await admit_discovered_urls(ctx, parsed.feed_links)
    if parsed.content:
        submit_started_at = time.perf_counter()
        index_result = await submit_html_page_to_indexer(ctx, parsed)
        timings.submit_ms = elapsed_ms(submit_started_at)
        if parsed.outlinks:
            await admit_discovered_urls(ctx, parsed.outlinks)
        timings.total_ms = elapsed_ms(total_started_at)
        if index_result.ok:
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                ctx.url,
                CrawlAttemptStatus.QUEUED_FOR_INDEX,
                index_result.status_code or 202,
                f"job_id={index_result.job_id}" if index_result.job_id else None,
                **timing_kwargs(timings),
            )
            await run_in_db_executor(
                ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.DONE
            )
            return PipelineProcessResult(
                status="queued_for_index",
                message="Page queued for indexing",
                job_id=index_result.job_id,
                outlinks_discovered=outlinks_discovered,
                timings=timings,
            )

        error_message = index_result.detail or "Indexer API rejected"
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.INDEXER_ERROR,
            index_result.status_code or 500,
            error_message,
            **timing_kwargs(timings),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return PipelineProcessResult(
            status="failed",
            message=error_message,
            outlinks_discovered=outlinks_discovered,
            timings=timings,
        )

    if parsed.outlinks:
        await admit_discovered_urls(ctx, parsed.outlinks)
    timings.total_ms = elapsed_ms(total_started_at)
    await run_in_db_executor(
        history_log.log_crawl_attempt,
        ctx.url,
        CrawlAttemptStatus.SKIPPED,
        200,
        "No main content found",
        **timing_kwargs(timings),
    )
    await run_in_db_executor(
        ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.DONE
    )
    return PipelineProcessResult(
        status="skipped",
        message="No main content found",
        outlinks_discovered=outlinks_discovered,
        timings=timings,
    )
