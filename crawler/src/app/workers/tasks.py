"""
Background Crawler Tasks

Main worker loop that fetches URLs from UrlStore and crawls them.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
import aiohttp
from cachetools import TTLCache

from app.core.crawl_denylist import load_crawl_denylist
from app.db.executor import run_in_db_executor
from app.db.url_store import UrlStore
from app.db.url_types import get_domain
from app.scheduler import Scheduler, SchedulerConfig
from app.core.config import settings
from app.utils.robots import AsyncRobotsCache
from app.utils import history as history_log
from app.workers.pipeline import (
    PipelineContext,
    _non_html_reason,
    discover_and_enqueue_links,
    fetch,
    parse,
    precheck,
    submit_to_indexer,
)
from shared.contracts.enums import CrawlAttemptStatus, CrawlUrlStatus

logger = logging.getLogger(__name__)

# Maximum retries for failed URLs
MAX_RETRIES = 3

# Robots block filter refresh interval (10 minutes)
ROBOTS_BLOCK_REFRESH_SECS = 600


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


async def process_url(
    session: aiohttp.ClientSession,
    robots: AsyncRobotsCache,
    url_store: UrlStore,
    scheduler: Scheduler,
    url: str,
    runtime_state: WorkerRuntimeState | None = None,
    indexer_session: aiohttp.ClientSession | None = None,
):
    """
    Process a single URL: check robots, fetch, parse, submit to indexer, extract links.
    """
    state = runtime_state or WorkerRuntimeState()
    domain = get_domain(url)
    host_error = False

    ctx = PipelineContext(
        session=session,
        indexer_session=indexer_session,
        robots=robots,
        url_store=url_store,
        scheduler=scheduler,
        url=url,
        domain=domain,
        blocked_domains=state.blocked_domains,
        domain_cache=state.domain_cache,
    )

    try:
        # Stage 1: Pre-fetch checks
        skip = await precheck(ctx)
        if skip:
            return

        # Stage 2: HTTP fetch
        result = await fetch(ctx)

        if result.error:
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.SKIPPED,
                result.status,
                result.error,
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
            return

        if result.status == 200 and result.body is not None:
            # Stage 3: Parse HTML
            html = result.body
            result.body = None  # release HTML reference early
            parsed = await parse(html, url, settings.CRAWL_OUTLINKS_PER_PAGE)
            del html

            if parsed.content:
                # Stage 4: Submit to indexer
                ok = await submit_to_indexer(ctx, parsed)
                if ok:
                    state.retry_counts.pop(url, None)
            else:
                await run_in_db_executor(
                    history_log.log_crawl_attempt,
                    url,
                    CrawlAttemptStatus.SKIPPED,
                    200,
                    "No main content found",
                )
                await run_in_db_executor(url_store.record, url, CrawlUrlStatus.DONE)

            # Stage 5: Discover and enqueue links
            if parsed.outlinks:
                await discover_and_enqueue_links(ctx, parsed.outlinks)

        elif result.status == 200:
            # Non-HTML content
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.SKIPPED,
                result.status,
                _non_html_reason(result.content_type),
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.DONE)

        elif result.status in (429, 500, 502, 503, 504):
            # Retryable errors
            host_error = True
            logger.warning("Retryable error %d for %s", result.status, url)
            await _handle_retry(url, url_store, f"HTTP {result.status}", state)

        else:
            # Other HTTP errors (404, etc)
            logger.warning("HTTP error %d for %s", result.status, url)
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.HTTP_ERROR,
                result.status,
                "HTTP Error",
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        host_error = True
        logger.warning("Network error for %s: %s", url, e)
        await _handle_retry(url, url_store, str(e), state)

    except Exception as e:
        host_error = True
        logger.error("Unexpected error processing %s: %s", url, e, exc_info=True)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.UNKNOWN_ERROR,
            error_message=str(e),
        )
        await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)

    finally:
        # Always record completion for rate limiting
        scheduler.record_complete(domain, success=not host_error)


async def _handle_retry(
    url: str,
    url_store: UrlStore,
    error: str,
    runtime_state: WorkerRuntimeState,
):
    """Handle retry logic for failed URLs."""
    retry_count = runtime_state.retry_counts.get(url, 0) + 1
    runtime_state.retry_counts[url] = retry_count

    if retry_count >= MAX_RETRIES:
        logger.warning("Moving to failed after %d retries: %s", retry_count, url)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.DEAD_LETTER,
            error_message=f"Max retries ({MAX_RETRIES}) exceeded: {error}",
        )
        await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
        runtime_state.retry_counts.pop(url, None)
    else:
        # Re-add to crawl queue for retry
        await run_in_db_executor(url_store.requeue, url)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.RETRY_LATER,
            error_message=f"{error} (retry {retry_count}/{MAX_RETRIES})",
        )


async def worker_loop(concurrency: int = 1, active_counter=None):
    """
    Main crawler worker loop with domain-parallel batch dispatch.

    Args:
        concurrency: Number of concurrent crawl tasks
        active_counter: Optional ActiveTaskCounter shared with WorkerService

    Fetches batches of URLs from different domains via Scheduler and
    dispatches them concurrently, maximising throughput across domains.
    """
    from app.services.worker import ActiveTaskCounter

    if active_counter is not None and not isinstance(active_counter, ActiveTaskCounter):
        active_counter = None

    logger.info("Worker loop started with concurrency=%d", concurrency)

    # Initialize history log database
    await run_in_db_executor(history_log.init_db)

    # Initialize UrlStore
    url_store = UrlStore(
        settings.CRAWLER_DB_PATH,
        recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
    )

    # Initialize Scheduler with rate limiting
    scheduler_config = SchedulerConfig(
        domain_min_interval=settings.SCHEDULER_DOMAIN_MIN_INTERVAL,
        domain_max_concurrent=settings.SCHEDULER_DOMAIN_MAX_CONCURRENT,
        batch_size=settings.SCHEDULER_BATCH_SIZE,
    )
    scheduler = Scheduler(url_store, scheduler_config)

    # Load static crawler denylist
    static_denylist = load_crawl_denylist(settings.CRAWL_DENYLIST_PATH)
    logger.info("Static crawler denylist: %d domains", len(static_denylist))
    scheduler.set_denied_domains(static_denylist)

    # Layer 3: Purge existing pending URLs from blocked domains
    if static_denylist:
        purged = await run_in_db_executor(
            url_store.purge_denied_domains, static_denylist
        )
        if purged:
            logger.info("Purged %d pending URLs from denied domains", purged)

    runtime_state = WorkerRuntimeState(blocked_domains=static_denylist)
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
                    scheduler,
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
                    scheduler.set_temporarily_blocked_domains(dynamic_blocked)

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
                    scheduler.get_ready_urls, available_slots
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
                    scheduler.record_start(item.domain)

                    try:
                        task = asyncio.create_task(
                            process_task(item.url, runtime_state)
                        )
                        in_flight_tasks.add(task)
                        task.add_done_callback(_on_task_done)
                    except Exception as e:
                        scheduler.record_complete(item.domain, success=False)
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
