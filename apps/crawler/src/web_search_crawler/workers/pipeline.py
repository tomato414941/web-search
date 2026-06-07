"""
Pipeline stages for URL processing.

Each stage is an independently testable async function.
`process_url` in tasks.py orchestrates these stages.
"""

import logging
import time

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.core.config import settings
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.services.fetchers import (
    FetchResult,
    _is_feed_content_type,
)
from web_search_crawler.services.feed_processing import process_feed_result
from web_search_crawler.services.html_processing import process_html_result
from web_search_crawler.utils import history as history_log
from web_search_crawler.workers.types import (
    CrawlStageTimings,
    PipelineContext,
    PipelineProcessResult,
)
from web_search_crawler.workers.timing import elapsed_ms, timing_kwargs
from web_search_contracts.enums import CrawlAttemptStatus, CrawlUrlStatus
from web_search_core.utils import MAX_URL_LENGTH, resolve_is_private_async

logger = logging.getLogger(__name__)


def _non_html_reason(content_type: str) -> str:
    normalized = content_type.strip() or "unknown"
    return f"Non-HTML content-type: {normalized}"


async def precheck(
    ctx: PipelineContext,
    timings: CrawlStageTimings | None = None,
) -> str | None:
    """Run pre-fetch checks (denylist, URL length, robots, SSRF).

    Returns a skip reason string if the URL should not be fetched,
    or None to proceed. Side-effects: logs and records skips.
    """
    started_at = time.perf_counter()
    timings = timings or CrawlStageTimings()

    if is_domain_denied(ctx.domain, ctx.blocked_domains):
        elapsed = elapsed_ms(started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="Domain denied by crawl denylist",
            **timing_kwargs(CrawlStageTimings(precheck_ms=elapsed, total_ms=elapsed)),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return "blocked"

    if len(ctx.url) > MAX_URL_LENGTH:
        elapsed = elapsed_ms(started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.SKIPPED,
            error_message=f"URL too long: {len(ctx.url)} > {MAX_URL_LENGTH}",
            **timing_kwargs(CrawlStageTimings(precheck_ms=elapsed, total_ms=elapsed)),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return "url_too_long"

    robots_started_at = time.perf_counter()
    if not await ctx.robots.can_fetch(ctx.url, settings.CRAWL_USER_AGENT):
        timings.robots_ms = elapsed_ms(robots_started_at)
        logger.info("Blocked by robots.txt: %s", ctx.url)
        elapsed = elapsed_ms(started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="Blocked by robots.txt",
            **timing_kwargs(
                CrawlStageTimings(
                    precheck_ms=elapsed,
                    robots_ms=timings.robots_ms,
                    total_ms=elapsed,
                )
            ),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return "robots_blocked"
    timings.robots_ms = elapsed_ms(robots_started_at)

    ssrf_started_at = time.perf_counter()
    if await resolve_is_private_async(ctx.domain):
        timings.ssrf_ms = elapsed_ms(ssrf_started_at)
        logger.warning("SSRF blocked: %s resolves to private IP", ctx.url)
        elapsed = elapsed_ms(started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="SSRF: private IP",
            **timing_kwargs(
                CrawlStageTimings(
                    precheck_ms=elapsed,
                    robots_ms=timings.robots_ms,
                    ssrf_ms=timings.ssrf_ms,
                    total_ms=elapsed,
                )
            ),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return "ssrf_blocked"
    timings.ssrf_ms = elapsed_ms(ssrf_started_at)

    crawl_delay_started_at = time.perf_counter()
    crawl_delay = ctx.robots.get_crawl_delay(ctx.domain, settings.CRAWL_USER_AGENT)
    if crawl_delay is not None:
        await run_in_db_executor(
            ctx.url_store.set_domain_crawl_delay,
            ctx.domain,
            crawl_delay,
        )
    timings.crawl_delay_ms = elapsed_ms(crawl_delay_started_at)

    return None


async def fetch(ctx: PipelineContext) -> FetchResult:
    """Perform the HTTP fetch and return the result.

    Does NOT log/record — the caller handles response-level decisions.
    """
    return await ctx.fetcher.fetch(ctx.session, ctx.url)


async def process_fetch_result(
    ctx: PipelineContext,
    result: FetchResult,
    *,
    max_outlinks: int,
    timings: CrawlStageTimings | None = None,
    total_started_at: float | None = None,
    retryable_statuses: tuple[int, ...] = (),
) -> PipelineProcessResult:
    """Handle fetch output and return a normalized crawl outcome."""
    timings = timings or CrawlStageTimings()
    total_started_at = total_started_at or time.perf_counter()
    if result.error:
        timings.total_ms = elapsed_ms(total_started_at)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.SKIPPED,
            result.status,
            result.error,
            **timing_kwargs(timings),
        )
        await run_in_db_executor(
            ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
        )
        return PipelineProcessResult(
            status="failed", message=result.error, timings=timings
        )

    if result.status == 200 and result.body is not None:
        if _is_feed_content_type(result.content_type):
            return await process_feed_result(
                ctx,
                result,
                timings=timings,
                total_started_at=total_started_at,
            )

        html = result.body
        result.body = None
        return await process_html_result(
            ctx,
            html,
            max_outlinks=max_outlinks,
            timings=timings,
            total_started_at=total_started_at,
        )

    if result.status == 200:
        message = _non_html_reason(result.content_type)
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

    message = f"HTTP {result.status}"
    timings.total_ms = elapsed_ms(total_started_at)
    if result.status in retryable_statuses:
        return PipelineProcessResult(
            status="retry",
            message=message,
            host_error=True,
            timings=timings,
        )

    await run_in_db_executor(
        history_log.log_crawl_attempt,
        ctx.url,
        CrawlAttemptStatus.HTTP_ERROR,
        result.status,
        message,
        **timing_kwargs(timings),
    )
    await run_in_db_executor(
        ctx.url_store.record_crawl_task_result, ctx.url, CrawlUrlStatus.FAILED
    )
    return PipelineProcessResult(
        status="failed",
        message=message,
        host_error=result.status >= 500,
        timings=timings,
    )


async def execute_crawl(
    ctx: PipelineContext,
    *,
    max_outlinks: int,
    retryable_statuses: tuple[int, ...] = (),
) -> PipelineProcessResult:
    """Run precheck, fetch, and post-fetch processing for one URL."""
    total_started_at = time.perf_counter()
    timings = CrawlStageTimings()
    precheck_started_at = time.perf_counter()
    skip_reason = await precheck(ctx, timings)
    timings.precheck_ms = elapsed_ms(precheck_started_at)
    if skip_reason:
        return PipelineProcessResult(
            status="skipped",
            message=f"Crawl skipped: {skip_reason}",
            timings=CrawlStageTimings(
                precheck_ms=timings.precheck_ms,
                robots_ms=timings.robots_ms,
                ssrf_ms=timings.ssrf_ms,
                crawl_delay_ms=timings.crawl_delay_ms,
                total_ms=timings.precheck_ms,
            ),
        )

    fetch_started_at = time.perf_counter()
    fetch_result = await fetch(ctx)
    timings.fetch_ms = elapsed_ms(fetch_started_at)
    timings.fetch_request_ms = fetch_result.fetch_request_ms
    timings.fetch_body_read_ms = fetch_result.fetch_body_read_ms
    return await process_fetch_result(
        ctx,
        fetch_result,
        max_outlinks=max_outlinks,
        timings=timings,
        total_started_at=total_started_at,
        retryable_statuses=retryable_statuses,
    )
