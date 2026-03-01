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

from app.core.blocklist import is_domain_blocked, load_domain_blocklist
from app.db.executor import run_in_db_executor
from app.db.url_store import UrlStore, get_domain
from app.scheduler import Scheduler, SchedulerConfig
from app.domain.scoring import (
    calculate_url_score,
    domain_rank_cache_size,
    load_domain_rank_cache,
    get_domain_rank,
)
from app.core.config import settings
from app.utils.parser import html_to_doc, extract_links
from app.utils.robots import AsyncRobotsCache
from app.services.indexer import submit_page_to_indexer
from app.utils import history as history_log
from shared.contracts.enums import CrawlAttemptStatus, CrawlUrlStatus
from shared.core.utils import MAX_URL_LENGTH, resolve_is_private_async

logger = logging.getLogger(__name__)

# Maximum response size (10 MB)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024

# Domain rank cache refresh interval (30 minutes)
DOMAIN_RANK_REFRESH_SECS = 1800

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


def _is_html_content_type(content_type: str) -> bool:
    return "text/html" in content_type or "application/xhtml" in content_type


def _non_html_reason(content_type: str) -> str:
    normalized = content_type.strip() or "unknown"
    return f"Non-HTML content-type: {normalized}"


async def process_url(
    session: aiohttp.ClientSession,
    robots: AsyncRobotsCache,
    url_store: UrlStore,
    scheduler: Scheduler,
    url: str,
    priority: float,
    runtime_state: WorkerRuntimeState | None = None,
):
    """
    Process a single URL: check robots, fetch, parse, submit to indexer, extract links.
    """
    state = runtime_state or WorkerRuntimeState()
    domain = get_domain(url)
    host_error = False

    try:
        # 0. Check static + dynamic blocklist (skip before any network I/O)
        if is_domain_blocked(domain, state.blocked_domains):
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.BLOCKED,
                error_message="Domain blocklisted",
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
            return

        if len(url) > MAX_URL_LENGTH:
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.SKIPPED,
                error_message=f"URL too long: {len(url)} > {MAX_URL_LENGTH}",
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
            return

        # 1. Check robots.txt
        if not await robots.can_fetch(url, settings.CRAWL_USER_AGENT):
            logger.info(f"Blocked by robots.txt: {url}")
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.BLOCKED,
                error_message="Blocked by robots.txt",
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
            return

        # SSRF check: resolve hostname and block private IPs
        if await resolve_is_private_async(domain):
            logger.warning(f"SSRF blocked: {url} resolves to private IP")
            await run_in_db_executor(
                history_log.log_crawl_attempt,
                url,
                CrawlAttemptStatus.BLOCKED,
                error_message="SSRF: private IP",
            )
            await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
            return

        # Apply Crawl-delay from robots.txt
        crawl_delay = robots.get_crawl_delay(domain, settings.CRAWL_USER_AGENT)
        if crawl_delay is not None:
            scheduler.set_crawl_delay(domain, crawl_delay)

        # 2. Fetch HTML
        async with session.get(
            url, timeout=settings.CRAWL_TIMEOUT_SEC, allow_redirects=True
        ) as resp:
            ct = resp.headers.get("Content-Type", "").lower()

            # Check Content-Length if available
            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_RESPONSE_SIZE:
                        logger.warning(
                            f"Response too large ({content_length} bytes): {url}"
                        )
                        await run_in_db_executor(
                            history_log.log_crawl_attempt,
                            url,
                            CrawlAttemptStatus.SKIPPED,
                            resp.status,
                            f"Response too large: {content_length} bytes",
                        )
                        await run_in_db_executor(
                            url_store.record, url, CrawlUrlStatus.FAILED
                        )
                        return
                except ValueError:
                    pass

            if resp.status == 200 and _is_html_content_type(ct):
                # Read with size limit
                body = await resp.content.read(MAX_RESPONSE_SIZE)
                if len(body) >= MAX_RESPONSE_SIZE:
                    logger.warning(
                        f"Response truncated at {MAX_RESPONSE_SIZE} bytes: {url}"
                    )
                    await run_in_db_executor(
                        history_log.log_crawl_attempt,
                        url,
                        CrawlAttemptStatus.SKIPPED,
                        resp.status,
                        f"Response truncated at {MAX_RESPONSE_SIZE} bytes",
                    )
                    await run_in_db_executor(
                        url_store.record, url, CrawlUrlStatus.FAILED
                    )
                    return

                html = body.decode("utf-8", errors="replace")

                # 3. Parse HTML (offload to executor)
                loop = asyncio.get_running_loop()
                title, content = await loop.run_in_executor(None, html_to_doc, html)

                # 5. Extract & Enqueue Links (moved before indexer submit to include in payload)
                discovered = await loop.run_in_executor(None, extract_links, url, html)
                if discovered:
                    discovered = discovered[: settings.CRAWL_OUTLINKS_PER_PAGE]

                if content:
                    # 4. Submit to Indexer queue API (with outlinks)
                    indexer_result = await submit_page_to_indexer(
                        session,
                        settings.INDEXER_API_URL,
                        settings.INDEXER_API_KEY,
                        url,
                        title,
                        content,
                        outlinks=discovered or [],
                    )

                    if indexer_result.ok:
                        # Clear retry count on success
                        state.retry_counts.pop(url, None)
                        await run_in_db_executor(
                            history_log.log_crawl_attempt,
                            url,
                            CrawlAttemptStatus.QUEUED_FOR_INDEX,
                            indexer_result.status_code or 202,
                            (
                                f"job_id={indexer_result.job_id}"
                                if indexer_result.job_id
                                else None
                            ),
                        )
                        await run_in_db_executor(
                            url_store.record, url, CrawlUrlStatus.DONE
                        )
                    else:
                        http_code = indexer_result.status_code or 500
                        error_message = (
                            indexer_result.detail
                            or f"Indexer API rejected ({http_code})"
                        )
                        await run_in_db_executor(
                            history_log.log_crawl_attempt,
                            url,
                            CrawlAttemptStatus.INDEXER_ERROR,
                            http_code,
                            error_message,
                        )
                        await run_in_db_executor(
                            url_store.record, url, CrawlUrlStatus.FAILED
                        )
                else:
                    await run_in_db_executor(
                        history_log.log_crawl_attempt,
                        url,
                        CrawlAttemptStatus.SKIPPED,
                        200,
                        "No main content found",
                    )
                    await run_in_db_executor(url_store.record, url, CrawlUrlStatus.DONE)

                # 6. Enqueue discovered links (batch insert)
                if discovered:
                    # Batch-fetch domain done counts for uncached domains
                    uncached_domains = {
                        get_domain(u)
                        for u in discovered
                        if get_domain(u) not in state.domain_cache
                    }
                    if uncached_domains:
                        counts = await run_in_db_executor(
                            url_store.domain_done_count_batch,
                            list(uncached_domains),
                        )
                        for d in uncached_domains:
                            state.domain_cache[d] = counts.get(d, 0)

                    scored_items: list[tuple[str, float]] = []
                    for new_url in discovered:
                        new_domain = get_domain(new_url)
                        if is_domain_blocked(new_domain, state.blocked_domains):
                            continue
                        domain_visits = max(state.domain_cache.get(new_domain, 0), 1)
                        dr = get_domain_rank(new_domain)
                        score = calculate_url_score(
                            new_url, priority, domain_visits, domain_pagerank=dr
                        )
                        scored_items.append((new_url, score))

                    await run_in_db_executor(url_store.add_batch_scored, scored_items)
                    logger.debug(
                        f"Enqueued links from {url} ({len(discovered)} discovered)"
                    )

            elif resp.status == 200:
                await run_in_db_executor(
                    history_log.log_crawl_attempt,
                    url,
                    CrawlAttemptStatus.SKIPPED,
                    resp.status,
                    _non_html_reason(ct),
                )
                await run_in_db_executor(url_store.record, url, CrawlUrlStatus.DONE)

            elif resp.status in (429, 500, 502, 503, 504):
                # Retryable errors
                host_error = True
                logger.warning(f"Retryable error {resp.status} for {url}")
                await _handle_retry(
                    url,
                    url_store,
                    priority,
                    f"HTTP {resp.status}",
                    state,
                )

            else:
                # Other HTTP errors (404, etc)
                logger.warning(f"HTTP error {resp.status} for {url}")
                await run_in_db_executor(
                    history_log.log_crawl_attempt,
                    url,
                    CrawlAttemptStatus.HTTP_ERROR,
                    resp.status,
                    "HTTP Error",
                )
                await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        host_error = True
        logger.warning(f"Network error for {url}: {e}")
        await _handle_retry(url, url_store, priority, str(e), state)

    except Exception as e:
        host_error = True
        logger.error(f"Unexpected error processing {url}: {e}", exc_info=True)
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
    priority: float,
    error: str,
    runtime_state: WorkerRuntimeState,
):
    """Handle retry logic for failed URLs."""
    retry_count = runtime_state.retry_counts.get(url, 0) + 1
    runtime_state.retry_counts[url] = retry_count

    if retry_count >= MAX_RETRIES:
        logger.warning(f"Moving to failed after {retry_count} retries: {url}")
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            url,
            CrawlAttemptStatus.DEAD_LETTER,
            error_message=f"Max retries ({MAX_RETRIES}) exceeded: {error}",
        )
        await run_in_db_executor(url_store.record, url, CrawlUrlStatus.FAILED)
        runtime_state.retry_counts.pop(url, None)
    else:
        # Transition crawling -> pending with lower priority
        new_priority = max(priority - 5.0, -100.0)
        await run_in_db_executor(url_store.requeue_for_retry, url, new_priority)
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

    logger.info(f"Worker loop started with concurrency={concurrency}")

    # Initialize history log database
    await run_in_db_executor(history_log.init_db)

    # Load domain PageRank cache (best-effort, empty if no data yet)
    await run_in_db_executor(load_domain_rank_cache, settings.DB_PATH)
    domain_rank_refreshed_at = time.monotonic()

    # Initialize UrlStore
    url_store = UrlStore(
        settings.CRAWLER_DB_PATH, recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS
    )

    # Recover stale crawling URLs from previous crash
    recovered = await run_in_db_executor(url_store.recover_stale_crawling)
    if recovered:
        logger.info(f"Recovered {recovered} stale crawling URLs back to pending")

    # Initialize Scheduler with rate limiting
    scheduler_config = SchedulerConfig(
        domain_min_interval=settings.SCHEDULER_DOMAIN_MIN_INTERVAL,
        domain_max_concurrent=settings.SCHEDULER_DOMAIN_MAX_CONCURRENT,
        batch_size=settings.SCHEDULER_BATCH_SIZE,
    )
    scheduler = Scheduler(url_store, scheduler_config)

    # Load static domain blocklist
    static_blocklist = load_domain_blocklist(settings.DOMAIN_BLOCKLIST_PATH)
    logger.info("Static domain blocklist: %d domains", len(static_blocklist))
    scheduler.set_blocked_domains(static_blocklist)

    # Layer 3: Purge existing pending URLs from blocked domains
    if static_blocklist:
        purged = await run_in_db_executor(
            url_store.purge_blocked_domains, static_blocklist
        )
        if purged:
            logger.info("Purged %d pending URLs from blocked domains", purged)

    runtime_state = WorkerRuntimeState(blocked_domains=static_blocklist)
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

    async with aiohttp.ClientSession(
        headers={"User-Agent": settings.CRAWL_USER_AGENT}, connector=connector
    ) as session:
        robots = AsyncRobotsCache(session, cache_size=settings.ROBOTS_CACHE_SIZE)

        logger.info(f"Crawler started with concurrency={concurrency}")
        logger.info(f"Submitting pages to: {settings.INDEXER_API_URL}")

        async def process_task(
            url: str, priority: float, state: WorkerRuntimeState
        ) -> None:
            try:
                await process_url(
                    session,
                    robots,
                    url_store,
                    scheduler,
                    url,
                    priority,
                    runtime_state=state,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error processing {url}: {e}")

        try:
            while True:
                # Periodic domain rank cache refresh
                if (
                    time.monotonic() - domain_rank_refreshed_at
                    > DOMAIN_RANK_REFRESH_SECS
                ):
                    old_count = domain_rank_cache_size()
                    await run_in_db_executor(load_domain_rank_cache, settings.DB_PATH)
                    domain_rank_refreshed_at = time.monotonic()
                    logger.info(
                        "Refreshed domain rank cache: %d -> %d entries",
                        old_count,
                        domain_rank_cache_size(),
                    )

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
                    # Combine static blocklist + dynamic robots-blocked
                    dynamic_blocked = frozenset(runtime_state.robots_blocked_domains)
                    combined = static_blocklist | dynamic_blocked
                    runtime_state.blocked_domains = combined
                    scheduler.set_blocked_domains(combined)

                    # Layer 3: Purge newly blocked domains from queue
                    new_dynamic = dynamic_blocked - static_blocklist
                    if new_dynamic:
                        purged = await run_in_db_executor(
                            url_store.purge_blocked_domains, frozenset(new_dynamic)
                        )
                        if purged:
                            logger.info(
                                "Purged %d pending URLs from newly blocked domains",
                                purged,
                            )

                    robots_block_refreshed_at = time.monotonic()
                    logger.info(
                        "Domain block filter: %d static + %d dynamic = %d total",
                        len(static_blocklist),
                        len(dynamic_blocked),
                        len(combined),
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
                    logger.info(
                        f"Processing: {item.url} (priority={item.priority:.1f})"
                    )
                    scheduler.record_start(item.domain)

                    try:
                        task = asyncio.create_task(
                            process_task(item.url, item.priority, runtime_state)
                        )
                        in_flight_tasks.add(task)
                        task.add_done_callback(_on_task_done)
                    except Exception as e:
                        scheduler.record_complete(item.domain, success=False)
                        logger.error(f"Failed to create task for {item.url}: {e}")

                _update_counter()

        except asyncio.CancelledError:
            logger.info("Worker loop cancelled")
            raise
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Worker loop error: {e}", exc_info=True)
            raise
        finally:
            if in_flight_tasks:
                logger.info(
                    f"Cancelling {len(in_flight_tasks)} in-flight crawl task(s)"
                )
                for task in list(in_flight_tasks):
                    task.cancel()
                await asyncio.gather(*in_flight_tasks, return_exceptions=True)
                in_flight_tasks.clear()
            _update_counter()

    logger.info("Worker loop stopped")
