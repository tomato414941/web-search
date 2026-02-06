"""
Background Crawler Tasks

Main worker loop that fetches URLs from UrlStore and crawls them.
"""

import asyncio
import logging
import aiohttp

from app.db.url_store import UrlStore, get_domain
from app.scheduler import Scheduler, SchedulerConfig
from app.domain.scoring import calculate_url_score
from app.core.config import settings
from app.utils.parser import html_to_doc, extract_links
from app.utils.robots import AsyncRobotsCache
from app.services.indexer import submit_page_to_indexer
from app.utils import history as history_log

logger = logging.getLogger(__name__)

# Maximum response size (10 MB)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024

# Maximum retries for failed URLs
MAX_RETRIES = 3

# Track retry counts in memory (reset on restart)
_retry_counts: dict[str, int] = {}


async def process_url(
    session: aiohttp.ClientSession,
    robots: AsyncRobotsCache,
    url_store: UrlStore,
    scheduler: Scheduler,
    url: str,
    priority: float,
):
    """
    Process a single URL: check robots, fetch, parse, submit to indexer, extract links.
    """
    domain = get_domain(url)

    try:
        # 1. Check robots.txt
        if not await robots.can_fetch(url, settings.CRAWL_USER_AGENT):
            logger.info(f"Blocked by robots.txt: {url}")
            history_log.log_crawl_attempt(
                url, "blocked", error_message="Blocked by robots.txt"
            )
            url_store.record(url, status="failed")
            return

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
                        history_log.log_crawl_attempt(
                            url,
                            "skipped",
                            resp.status,
                            f"Response too large: {content_length} bytes",
                        )
                        url_store.record(url, status="failed")
                        return
                except ValueError:
                    pass

            if resp.status == 200 and ("text/html" in ct or "application/xhtml" in ct):
                # Read with size limit
                body = await resp.content.read(MAX_RESPONSE_SIZE)
                if len(body) >= MAX_RESPONSE_SIZE:
                    logger.warning(
                        f"Response truncated at {MAX_RESPONSE_SIZE} bytes: {url}"
                    )
                    history_log.log_crawl_attempt(
                        url,
                        "skipped",
                        resp.status,
                        f"Response truncated at {MAX_RESPONSE_SIZE} bytes",
                    )
                    url_store.record(url, status="failed")
                    return

                html = body.decode("utf-8", errors="replace")

                # 3. Parse HTML (offload to executor)
                loop = asyncio.get_running_loop()
                title, content = await loop.run_in_executor(None, html_to_doc, html)

                if content:
                    # 4. Submit to Indexer API
                    success = await submit_page_to_indexer(
                        session,
                        settings.INDEXER_API_URL,
                        settings.INDEXER_API_KEY,
                        url,
                        title,
                        content,
                    )

                    if success:
                        # Clear retry count on success
                        _retry_counts.pop(url, None)
                        history_log.log_crawl_attempt(url, "indexed", 200)
                        url_store.record(url, status="done")
                    else:
                        history_log.log_crawl_attempt(
                            url, "indexer_error", 500, "Indexer API rejected"
                        )
                        url_store.record(url, status="failed")
                else:
                    history_log.log_crawl_attempt(
                        url, "skipped", 200, "No main content found"
                    )
                    url_store.record(url, status="done")

                # 5. Extract & Enqueue Links
                discovered = await loop.run_in_executor(None, extract_links, url, html)

                if discovered:
                    # Limit outlinks
                    discovered = discovered[: settings.CRAWL_OUTLINKS_PER_PAGE]

                    # add() handles dedup + recrawl check internally
                    for new_url in discovered:
                        domain_visits = 1
                        score = calculate_url_score(new_url, priority, domain_visits)
                        url_store.add(new_url, priority=score, source_url=url)

                    logger.debug(
                        f"Enqueued links from {url} ({len(discovered)} discovered)"
                    )

            elif resp.status in (429, 500, 502, 503, 504):
                # Retryable errors
                logger.warning(f"Retryable error {resp.status} for {url}")
                await _handle_retry(url, url_store, priority, f"HTTP {resp.status}")

            else:
                # Other HTTP errors (404, etc)
                logger.warning(f"HTTP error {resp.status} for {url}")
                history_log.log_crawl_attempt(
                    url, "http_error", resp.status, "HTTP Error"
                )
                url_store.record(url, status="failed")

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(f"Network error for {url}: {e}")
        await _handle_retry(url, url_store, priority, str(e))

    except Exception as e:
        logger.error(f"Unexpected error processing {url}: {e}", exc_info=True)
        history_log.log_crawl_attempt(url, "unknown_error", error_message=str(e))
        url_store.record(url, status="failed")

    finally:
        # Always record completion for rate limiting
        scheduler.record_complete(domain)


async def _handle_retry(
    url: str,
    url_store: UrlStore,
    priority: float,
    error: str,
):
    """Handle retry logic for failed URLs."""
    retry_count = _retry_counts.get(url, 0) + 1
    _retry_counts[url] = retry_count

    if retry_count >= MAX_RETRIES:
        logger.warning(f"Moving to failed after {retry_count} retries: {url}")
        history_log.log_crawl_attempt(
            url,
            "dead_letter",
            error_message=f"Max retries ({MAX_RETRIES}) exceeded: {error}",
        )
        url_store.record(url, status="failed")
        _retry_counts.pop(url, None)
    else:
        # Re-add to url_store as pending with lower priority
        new_priority = max(priority - 5.0, -100.0)
        url_store.add(url, priority=new_priority)
        history_log.log_crawl_attempt(
            url,
            "retry_later",
            error_message=f"{error} (retry {retry_count}/{MAX_RETRIES})",
        )


async def worker_loop(concurrency: int = 1):
    """
    Main crawler worker loop.

    Args:
        concurrency: Number of concurrent crawl tasks

    Continuously fetches URLs from UrlStore via Scheduler and processes them.
    """
    logger.info(f"Worker loop started with concurrency={concurrency}")

    # Initialize history log database
    history_log.init_db()

    # Initialize UrlStore
    url_store = UrlStore(
        settings.CRAWLER_DB_PATH, recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS
    )

    # Recover stale crawling URLs from previous crash
    recovered = url_store.recover_stale_crawling()
    if recovered:
        logger.info(f"Recovered {recovered} stale crawling URLs back to pending")

    # Initialize Scheduler with rate limiting
    scheduler_config = SchedulerConfig(
        domain_min_interval=1.0,  # 1 second between requests to same domain
        domain_max_concurrent=2,  # Max 2 concurrent per domain
        batch_size=100,
    )
    scheduler = Scheduler(url_store, scheduler_config)

    sem = asyncio.Semaphore(concurrency)

    connector = aiohttp.TCPConnector(
        limit_per_host=5,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )

    async with aiohttp.ClientSession(
        headers={"User-Agent": settings.CRAWL_USER_AGENT}, connector=connector
    ) as session:
        # Create robots cache without Redis
        robots = AsyncRobotsCache(session, redis_client=None)

        logger.info(f"Crawler started with concurrency={concurrency}")
        logger.info(f"Submitting pages to: {settings.INDEXER_API_URL}")

        try:
            while True:
                # Get next URL from scheduler
                item = scheduler.get_next()

                if not item:
                    # No URLs ready, wait before checking again
                    await asyncio.sleep(1)
                    continue

                url = item.url
                priority = item.priority
                domain = item.domain

                logger.info(f"Processing: {url} (priority={priority:.1f})")

                # Record start for rate limiting
                scheduler.record_start(domain)

                # Process URL with semaphore concurrency control
                async def process_with_semaphore(url: str, priority: float, item):
                    try:
                        await process_url(
                            session, robots, url_store, scheduler, url, priority
                        )
                    except Exception as e:
                        logger.error(f"Error processing {url}: {e}")
                        scheduler.record_complete(item.domain)
                    finally:
                        sem.release()

                # Acquire semaphore for concurrency control
                await sem.acquire()

                # Create task for concurrent processing
                try:
                    asyncio.create_task(process_with_semaphore(url, priority, item))
                except Exception as e:
                    sem.release()
                    scheduler.record_complete(domain)
                    logger.error(f"Failed to create task for {url}: {e}")

        except asyncio.CancelledError:
            logger.info("Worker loop cancelled")
            raise
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Worker loop error: {e}", exc_info=True)
            raise

    logger.info("Worker loop stopped")
