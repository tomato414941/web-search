"""RSS/Atom feed processing for crawler fetch results."""

import time

from web_search_crawler.core.config import settings
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.services.fetchers import FetchResult
from web_search_crawler.services.indexer import (
    IndexerSubmitResult,
    submit_page_to_indexer,
)
from web_search_crawler.utils import history as history_log
from web_search_crawler.utils.parser import FeedEntry, parse_feed
from web_search_crawler.workers.types import (
    CrawlStageTimings,
    PipelineContext,
    PipelineProcessResult,
)
from web_search_crawler.workers.timing import elapsed_ms, timing_kwargs
from web_search_contracts.enums import CrawlAttemptStatus, CrawlUrlStatus


async def submit_feed_entry(
    ctx: PipelineContext,
    entry: FeedEntry,
) -> IndexerSubmitResult:
    return await submit_page_to_indexer(
        ctx.indexer_session or ctx.session,
        settings.INDEXER_API_URL,
        settings.INDEXER_API_KEY,
        entry.url,
        entry.title,
        entry.content,
        published_at=entry.published_at,
    )


async def process_feed_result(
    ctx: PipelineContext,
    result: FetchResult,
    *,
    timings: CrawlStageTimings,
    total_started_at: float,
) -> PipelineProcessResult:
    xml_text = result.body or ""
    result.body = None
    try:
        entries = parse_feed(xml_text)
    except Exception as exc:
        message = f"Feed parse failed: {exc}"
        timings.total_ms = elapsed_ms(total_started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.SKIPPED,
            result.status,
            message,
            **timing_kwargs(timings),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return PipelineProcessResult(status="failed", message=message, timings=timings)

    if not entries:
        message = "No feed entries found"
        timings.total_ms = elapsed_ms(total_started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.SKIPPED,
            result.status,
            message,
            **timing_kwargs(timings),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.DONE
        )
        return PipelineProcessResult(status="skipped", message=message, timings=timings)

    entry_urls = [entry.url for entry in entries]
    await run_in_db_executor(
        ctx.link_graph.replace_observed_links,
        ctx.url,
        entry_urls,
    )
    if entry_urls:
        await run_in_db_executor(
            ctx.url_ledger.record_discovered_urls,
            entry_urls,
        )

    submit_started_at = time.perf_counter()
    submitted = 0
    for entry in entries:
        index_result = await submit_feed_entry(ctx, entry)
        if index_result.ok:
            submitted += 1
    timings.submit_ms = elapsed_ms(submit_started_at)

    if submitted == 0:
        message = "Feed entries failed to index"
        timings.total_ms = elapsed_ms(total_started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.INDEXER_ERROR,
            result.status,
            message,
            **timing_kwargs(timings),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return PipelineProcessResult(status="failed", message=message, timings=timings)

    timings.total_ms = elapsed_ms(total_started_at)
    await run_in_db_executor(
        history_log.log_crawl_attempt,
        ctx.url,
        CrawlAttemptStatus.QUEUED_FOR_INDEX,
        result.status,
        f"feed_entries={submitted}",
        **timing_kwargs(timings),
    )
    await run_in_db_executor(
        ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.DONE
    )
    return PipelineProcessResult(
        status="queued_for_index",
        message="Feed entries queued for indexing",
        outlinks_discovered=submitted,
        timings=timings,
    )
