"""One-off crawl execution for authenticated operators."""

import aiohttp
from dataclasses import dataclass
from typing import Literal

from web_search_crawler.core.config import settings
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.db.url_store import UrlStore
from web_search_crawler.services.crawl_runtime import (
    build_frontier_planner,
    load_static_crawl_config,
)
from web_search_crawler.utils import history as history_log
from web_search_crawler.utils.robots import AsyncRobotsCache
from web_search_crawler.workers.pipeline import (
    execute_crawl,
)
from web_search_crawler.workers.types import PipelineContext
from web_search_contracts.enums import CrawlAttemptStatus, CrawlUrlStatus


@dataclass(frozen=True)
class ImmediateCrawlResult:
    status: Literal["submitted", "skipped", "failed", "busy"]
    url: str
    message: str
    job_id: str | None = None
    outlinks_discovered: int = 0


def _normalize_public_crawl_result(
    status: str,
    message: str,
    *,
    job_id: str | None = None,
    outlinks_discovered: int = 0,
) -> tuple[str, str, str | None, int]:
    if status == "queued_for_index":
        return ("submitted", "Page submitted to indexer", job_id, outlinks_discovered)
    if status == "retry":
        return ("failed", message, None, outlinks_discovered)
    if status in {"skipped", "failed", "busy"}:
        return (status, message, job_id, outlinks_discovered)
    return ("failed", message or "Unknown crawl result", None, outlinks_discovered)


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
    """Fetch a single URL immediately and submit the parsed page to the indexer."""
    await run_in_db_executor(history_log.init_db)

    store = url_store or UrlStore(
        settings.CRAWLER_DB_PATH,
        recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
    )
    planner = build_frontier_planner(store, batch_size=1)
    blocked_domains, url_filter = load_static_crawl_config(planner)
    leased = await run_in_db_executor(store.lease_manual_url, url)
    if not leased:
        return ImmediateCrawlResult(
            status="busy",
            url=url,
            message="URL is already leased by another crawl",
        )

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
            planner=planner,
            url=url,
            blocked_domains=blocked_domains,
            url_filter=url_filter,
            domain_cache={},
        )

        try:
            outcome = await execute_crawl(
                ctx,
                max_outlinks=settings.CRAWL_OUTLINKS_PER_PAGE,
            )
            public_status, public_message, public_job_id, public_outlinks = (
                _normalize_public_crawl_result(
                    outcome.status,
                    outcome.message,
                    job_id=outcome.job_id,
                    outlinks_discovered=outcome.outlinks_discovered,
                )
            )
            return ImmediateCrawlResult(
                status=public_status,
                url=url,
                message=public_message,
                job_id=public_job_id,
                outlinks_discovered=public_outlinks,
            )
        except (aiohttp.ClientError, TimeoutError) as exc:
            message = str(exc) or exc.__class__.__name__
            await _log_attempt(url, CrawlAttemptStatus.UNKNOWN_ERROR, message=message)
            await run_in_db_executor(
                store.record_crawl_result, url, CrawlUrlStatus.FAILED
            )
            return ImmediateCrawlResult(status="failed", url=url, message=message)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            await _log_attempt(url, CrawlAttemptStatus.UNKNOWN_ERROR, message=message)
            await run_in_db_executor(
                store.record_crawl_result, url, CrawlUrlStatus.FAILED
            )
            return ImmediateCrawlResult(status="failed", url=url, message=message)
        finally:
            entry = await run_in_db_executor(store.get_frontier_entry, url)
            if entry is not None and entry.status == "leased":
                await run_in_db_executor(store.release_frontier_urls, [url])
