"""
Background Crawler Tasks

Main worker loop that fetches URLs from UrlStore and crawls them.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from cachetools import TTLCache

from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.core.config import settings
from web_search_crawler.db.url_store import UrlStore
from web_search_crawler.frontier_planner import FrontierPlanner
from web_search_crawler.services.crawl_runtime import (
    build_frontier_planner,
    build_url_store,
    load_static_crawl_config,
)
from web_search_crawler.utils.robots import AsyncRobotsCache
from web_search_crawler.utils import history as history_log
from web_search_crawler.workers.pipeline import (
    execute_crawl,
)
from web_search_crawler.workers.types import (
    CrawlStageTimings,
    PipelineContext,
)
from web_search_contracts.enums import CrawlAttemptStatus, CrawlUrlStatus

logger = logging.getLogger(__name__)

# Maximum retries for failed URLs
MAX_RETRIES = 3

# Robots block filter refresh interval (10 minutes)
ROBOTS_BLOCK_REFRESH_SECS = 600
RETRYABLE_HTTP_STATUSES = (429, 500, 502, 503, 504)


DOMAIN_CACHE_MAX = 50000
DOMAIN_CACHE_TTL = 3600  # 1 hour


@dataclass
class WorkerRuntimeState:
    retry_counts: dict[str, int] = field(default_factory=dict)
    domain_cache: TTLCache = field(
        default_factory=lambda: TTLCache(maxsize=DOMAIN_CACHE_MAX, ttl=DOMAIN_CACHE_TTL)
    )
    robots_blocked_domains: set[str] = field(default_factory=set)
    blocked_domains: frozenset[str] = field(default_factory=frozenset)
    url_filter: Any = None


async def process_url(
    session: aiohttp.ClientSession,
    robots: AsyncRobotsCache,
    url_store: UrlStore,
    planner: FrontierPlanner,
    url: str,
    runtime_state: WorkerRuntimeState | None = None,
    indexer_session: aiohttp.ClientSession | None = None,
):
    """
    Process a single URL: check robots, fetch, parse, submit to indexer, extract links.
    """
    state = runtime_state or WorkerRuntimeState()

    ctx = PipelineContext(
        session=session,
        indexer_session=indexer_session,
        robots=robots,
        url_store=url_store,
        planner=planner,
        url=url,
        blocked_domains=state.blocked_domains,
        url_filter=state.url_filter,
        domain_cache=state.domain_cache,
    )

    try:
        await run_in_db_executor(
            url_store.record_discovered_url,
            url,
        )
        outcome = await execute_crawl(
            ctx,
            max_outlinks=settings.CRAWL_OUTLINKS_PER_PAGE,
            retryable_statuses=RETRYABLE_HTTP_STATUSES,
        )
        if outcome.status == "queued_for_index":
            state.retry_counts.pop(url, None)
            return
        if outcome.status == "retry":
            logger.warning("Retryable error for %s: %s", url, outcome.message)
            await _handle_retry(
                url,
                url_store,
                outcome.message,
                state,
                timings=outcome.timings,
            )
            return
        if outcome.status in {"skipped", "failed"}:
            return

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning("Network error for %s: %s", url, e)
        await _handle_retry(url, url_store, str(e), state)

    except Exception as e:
        logger.error("Unexpected error processing %s: %s", url, e, exc_info=True)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.UNKNOWN_ERROR,
            error_message=str(e),
        )
        await run_in_db_executor(
            url_store.record_frontier_result, url, CrawlUrlStatus.FAILED
        )


async def _handle_retry(
    url: str,
    url_store: UrlStore,
    error: str,
    runtime_state: WorkerRuntimeState,
    timings: CrawlStageTimings | None = None,
):
    """Handle retry logic for failed URLs."""
    retry_count = runtime_state.retry_counts.get(url, 0) + 1
    runtime_state.retry_counts[url] = retry_count
    timing_kwargs = {
        "precheck_ms": timings.precheck_ms if timings else None,
        "robots_ms": timings.robots_ms if timings else None,
        "ssrf_ms": timings.ssrf_ms if timings else None,
        "crawl_delay_ms": timings.crawl_delay_ms if timings else None,
        "fetch_ms": timings.fetch_ms if timings else None,
        "fetch_request_ms": timings.fetch_request_ms if timings else None,
        "fetch_body_read_ms": timings.fetch_body_read_ms if timings else None,
        "parse_ms": timings.parse_ms if timings else None,
        "submit_ms": timings.submit_ms if timings else None,
        "total_ms": timings.total_ms if timings else None,
    }

    if retry_count >= MAX_RETRIES:
        logger.warning("Moving to failed after %d retries: %s", retry_count, url)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.DEAD_LETTER,
            error_message=f"Max retries ({MAX_RETRIES}) exceeded: {error}",
            **timing_kwargs,
        )
        await run_in_db_executor(
            url_store.record_frontier_result, url, CrawlUrlStatus.FAILED
        )
        runtime_state.retry_counts.pop(url, None)
    else:
        # Re-release the leased frontier entry for retry
        await run_in_db_executor(url_store.requeue, url)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.RETRY_LATER,
            error_message=f"{error} (retry {retry_count}/{MAX_RETRIES})",
            **timing_kwargs,
        )


async def worker_loop(concurrency: int = 1, active_counter=None):
    """
    Main crawler worker loop with domain-parallel batch dispatch.

    Args:
        concurrency: Number of concurrent crawl tasks
        active_counter: Optional ActiveTaskCounter shared with WorkerService

    Fetches batches of URLs from different domains via the frontier planner and
    dispatches them concurrently, maximising throughput across domains.
    """
    from web_search_crawler.services.worker import ActiveTaskCounter

    if active_counter is not None and not isinstance(active_counter, ActiveTaskCounter):
        active_counter = None

    logger.info("Worker loop started with concurrency=%d", concurrency)

    # Initialize history log database
    await run_in_db_executor(history_log.init_db)

    url_store = build_url_store()
    planner = build_frontier_planner(
        url_store, batch_size=settings.FRONTIER_PLANNER_BATCH_SIZE
    )
    static_denylist, url_filter = load_static_crawl_config(planner)
    logger.info("Static crawler denylist: %d domains", len(static_denylist))

    # Layer 3: Purge existing pending URLs from blocked domains
    if static_denylist:
        purged = await run_in_db_executor(
            url_store.purge_denied_domains, static_denylist
        )
        if purged:
            logger.info("Purged %d pending URLs from denied domains", purged)

    runtime_state = WorkerRuntimeState(
        blocked_domains=static_denylist, url_filter=url_filter
    )
    robots_block_refreshed_at = 0.0  # Force immediate first load
    in_flight_tasks: set[asyncio.Task[None]] = set()

    def _update_counter():
        if active_counter is not None:
            active_counter.value = len(in_flight_tasks)

    def _on_task_done(t: asyncio.Task) -> None:
        in_flight_tasks.discard(t)
        _update_counter()

    connector = aiohttp.TCPConnector(
        limit=settings.CRAWL_TCP_LIMIT,
        limit_per_host=5,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )

    indexer_connector = aiohttp.TCPConnector(
        limit=max(16, concurrency * 2),
        limit_per_host=max(16, concurrency * 2),
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )

    async with (
        aiohttp.ClientSession(
            headers={"User-Agent": settings.CRAWL_USER_AGENT}, connector=connector
        ) as session,
        aiohttp.ClientSession(connector=indexer_connector) as indexer_session,
    ):
        robots = AsyncRobotsCache(session, cache_size=settings.ROBOTS_CACHE_SIZE)

        logger.info("Crawler started with concurrency=%d", concurrency)
        logger.info("Submitting pages to: %s", settings.INDEXER_API_URL)

        async def process_task(url: str, state: WorkerRuntimeState) -> None:
            try:
                await process_url(
                    session,
                    robots,
                    url_store,
                    planner,
                    url,
                    runtime_state=state,
                    indexer_session=indexer_session,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error processing %s: %s", url, e)

        try:
            while True:
                # Periodic robots block filter refresh
                if (
                    time.monotonic() - robots_block_refreshed_at
                    > ROBOTS_BLOCK_REFRESH_SECS
                ):
                    runtime_state.robots_blocked_domains = await run_in_db_executor(
                        history_log.get_robots_blocked_domains,
                        hours=settings.CRAWL_ROBOTS_BLOCK_WINDOW_HOURS,
                        min_count=settings.CRAWL_ROBOTS_BLOCK_MIN_COUNT,
                    )
                    dynamic_blocked = frozenset(runtime_state.robots_blocked_domains)
                    runtime_state.blocked_domains = static_denylist | dynamic_blocked
                    planner.set_temporarily_blocked_domains(dynamic_blocked)

                    robots_block_refreshed_at = time.monotonic()
                    logger.info(
                        "Domain block filter: %d static + %d dynamic = %d total",
                        len(static_denylist),
                        len(dynamic_blocked),
                        len(runtime_state.blocked_domains),
                    )

                # Calculate available concurrency slots
                available_slots = concurrency - len(in_flight_tasks)

                if available_slots <= 0:
                    # All slots occupied — wait for any task to finish
                    if in_flight_tasks:
                        await asyncio.wait(
                            in_flight_tasks,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    continue

                # Batch-fetch ready URLs from different domains
                ready_items = await run_in_db_executor(
                    planner.lease_ready_urls, available_slots
                )

                if not ready_items:
                    # No domains ready right now
                    if in_flight_tasks:
                        await asyncio.wait(
                            in_flight_tasks,
                            timeout=0.5,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    else:
                        await asyncio.sleep(0.5)
                    continue

                # Dispatch all ready URLs concurrently
                for item in ready_items:
                    logger.info("Processing: %s", item.url)

                    try:
                        task = asyncio.create_task(
                            process_task(item.url, runtime_state)
                        )
                        in_flight_tasks.add(task)
                        task.add_done_callback(_on_task_done)
                    except Exception as e:
                        logger.error("Failed to create task for %s: %s", item.url, e)

                _update_counter()

        except asyncio.CancelledError:
            logger.info("Worker loop cancelled")
            raise
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error("Worker loop error: %s", e, exc_info=True)
            raise
        finally:
            if in_flight_tasks:
                logger.info(
                    "Cancelling %d in-flight crawl task(s)", len(in_flight_tasks)
                )
                for task in list(in_flight_tasks):
                    task.cancel()
                await asyncio.gather(*in_flight_tasks, return_exceptions=True)
                in_flight_tasks.clear()
            _update_counter()

    logger.info("Worker loop stopped")
