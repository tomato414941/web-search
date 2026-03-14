"""One-off crawl execution for authenticated operators."""

import aiohttp
from dataclasses import dataclass

from app.core.config import settings
from app.core.crawl_denylist import load_crawl_denylist
from app.db.executor import run_in_db_executor
from app.db.url_store import UrlStore
from app.db.url_types import get_domain
from app.scheduler import Scheduler, SchedulerConfig
from app.services.indexer import submit_page_to_indexer
from app.utils import history as history_log
from app.utils.robots import AsyncRobotsCache
from app.workers.pipeline import (
    PipelineContext,
    _non_html_reason,
    discover_and_enqueue_links,
    fetch,
    parse,
    precheck,
)
from shared.contracts.enums import CrawlAttemptStatus, CrawlUrlStatus


@dataclass(frozen=True)
class ImmediateCrawlResult:
    status: str
    url: str
    message: str
    job_id: str | None = None
    outlinks_discovered: int = 0


async def _log_attempt(
    url: str,
    status: CrawlAttemptStatus,
    http_status: int | None = None,
    message: str | None = None,
) -> None:
    await run_in_db_executor(
        history_log.log_crawl_attempt,
        url,
        status,
        http_status,
        message,
    )


async def crawl_url_now(
    url: str, *, url_store: UrlStore | None = None
) -> ImmediateCrawlResult:
    """Fetch a single URL immediately and queue the parsed page for indexing."""
    await run_in_db_executor(history_log.init_db)

    store = url_store or UrlStore(
        settings.CRAWLER_DB_PATH,
        recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
    )
    scheduler = Scheduler(
        store,
        SchedulerConfig(
            domain_min_interval=settings.SCHEDULER_DOMAIN_MIN_INTERVAL,
            domain_max_concurrent=settings.SCHEDULER_DOMAIN_MAX_CONCURRENT,
            batch_size=1,
        ),
    )
    blocked_domains = load_crawl_denylist(settings.CRAWL_DENYLIST_PATH)
    scheduler.set_denied_domains(blocked_domains)
    domain = get_domain(url)
    host_error = False

    async with (
        aiohttp.ClientSession(
            headers={"User-Agent": settings.CRAWL_USER_AGENT}
        ) as session,
        aiohttp.ClientSession() as indexer_session,
    ):
        robots = AsyncRobotsCache(session, cache_size=settings.ROBOTS_CACHE_SIZE)
        ctx = PipelineContext(
            session=session,
            indexer_session=indexer_session,
            robots=robots,
            url_store=store,
            scheduler=scheduler,
            url=url,
            domain=domain,
            blocked_domains=blocked_domains,
            domain_cache={},
        )

        try:
            skip_reason = await precheck(ctx)
            if skip_reason:
                return ImmediateCrawlResult(
                    status="skipped",
                    url=url,
                    message=f"Crawl skipped: {skip_reason}",
                )

            result = await fetch(ctx)
            if result.error:
                await _log_attempt(
                    url,
                    CrawlAttemptStatus.SKIPPED,
                    result.status,
                    result.error,
                )
                await run_in_db_executor(store.record, url, CrawlUrlStatus.FAILED)
                return ImmediateCrawlResult(
                    status="failed",
                    url=url,
                    message=result.error,
                )

            if result.status == 200 and result.body is not None:
                parsed = await parse(result.body, url, settings.CRAWL_OUTLINKS_PER_PAGE)
                outlinks_discovered = len(parsed.outlinks)

                if parsed.content:
                    index_result = await submit_page_to_indexer(
                        ctx.indexer_session or ctx.session,
                        settings.INDEXER_API_URL,
                        settings.INDEXER_API_KEY or "",
                        url,
                        parsed.title,
                        parsed.content,
                        outlinks=parsed.outlinks,
                        published_at=parsed.published_at,
                        updated_at=parsed.updated_at,
                        author=parsed.author,
                        organization=parsed.organization,
                    )
                    if index_result.ok:
                        await _log_attempt(
                            url,
                            CrawlAttemptStatus.QUEUED_FOR_INDEX,
                            index_result.status_code or 202,
                            (
                                f"job_id={index_result.job_id}"
                                if index_result.job_id
                                else None
                            ),
                        )
                        await run_in_db_executor(store.record, url, CrawlUrlStatus.DONE)
                        if parsed.outlinks:
                            await discover_and_enqueue_links(ctx, parsed.outlinks)
                        return ImmediateCrawlResult(
                            status="queued_for_index",
                            url=url,
                            message="Page queued for indexing",
                            job_id=index_result.job_id,
                            outlinks_discovered=outlinks_discovered,
                        )

                    host_error = True
                    await _log_attempt(
                        url,
                        CrawlAttemptStatus.INDEXER_ERROR,
                        index_result.status_code or 500,
                        index_result.detail or "Indexer API rejected",
                    )
                    await run_in_db_executor(store.record, url, CrawlUrlStatus.FAILED)
                    return ImmediateCrawlResult(
                        status="failed",
                        url=url,
                        message=index_result.detail or "Indexer API rejected",
                        outlinks_discovered=outlinks_discovered,
                    )

                await _log_attempt(
                    url,
                    CrawlAttemptStatus.SKIPPED,
                    200,
                    "No main content found",
                )
                await run_in_db_executor(store.record, url, CrawlUrlStatus.DONE)
                if parsed.outlinks:
                    await discover_and_enqueue_links(ctx, parsed.outlinks)
                return ImmediateCrawlResult(
                    status="skipped",
                    url=url,
                    message="No main content found",
                    outlinks_discovered=outlinks_discovered,
                )

            if result.status == 200:
                message = _non_html_reason(result.content_type)
                await _log_attempt(
                    url, CrawlAttemptStatus.SKIPPED, result.status, message
                )
                await run_in_db_executor(store.record, url, CrawlUrlStatus.DONE)
                return ImmediateCrawlResult(
                    status="skipped",
                    url=url,
                    message=message,
                )

            host_error = result.status >= 500
            message = f"HTTP {result.status}"
            await _log_attempt(
                url, CrawlAttemptStatus.HTTP_ERROR, result.status, message
            )
            await run_in_db_executor(store.record, url, CrawlUrlStatus.FAILED)
            return ImmediateCrawlResult(
                status="failed",
                url=url,
                message=message,
            )
        except (aiohttp.ClientError, TimeoutError) as exc:
            host_error = True
            message = str(exc) or exc.__class__.__name__
            await _log_attempt(url, CrawlAttemptStatus.UNKNOWN_ERROR, message=message)
            await run_in_db_executor(store.record, url, CrawlUrlStatus.FAILED)
            return ImmediateCrawlResult(status="failed", url=url, message=message)
        except Exception as exc:
            host_error = True
            message = str(exc) or exc.__class__.__name__
            await _log_attempt(url, CrawlAttemptStatus.UNKNOWN_ERROR, message=message)
            await run_in_db_executor(store.record, url, CrawlUrlStatus.FAILED)
            return ImmediateCrawlResult(status="failed", url=url, message=message)
        finally:
            scheduler.record_complete(domain, success=not host_error)
