"""
Background Crawler Tasks

Main worker loop that dequeues URLs from Redis and crawls them.
"""

import asyncio
import logging
import aiohttp
from shared.db.redis import (
    get_redis,
    dequeue_top,
    enqueue_batch,
    increment_retry_count,
    clear_retry_count,
    move_to_dead_letter,
    MAX_RETRIES,
)
from app.domain.scoring import calculate_url_score
from app.core.config import settings
from app.utils.parser import html_to_doc, extract_links
from app.utils.robots import AsyncRobotsCache
from app.services.indexer import submit_page_to_indexer
from app.utils import history

logger = logging.getLogger(__name__)

# Maximum response size (10 MB)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024


async def process_url(
    session: aiohttp.ClientSession,
    robots: AsyncRobotsCache,
    redis_client,
    url: str,
    score: float,
):
    """
    Process a single URL: check robots, fetch, parse, submit to indexer, extract links

    Args:
        session: aiohttp client session
        robots: Robots.txt cache
        redis_client: Redis client
        url: URL to crawl
        score: Priority score
    """
    # 1. Check robots.txt
    if not await robots.can_fetch(url, settings.CRAWL_USER_AGENT):
        logger.info(f"🚫 Blocked by robots.txt: {url}")
        history.log_crawl_attempt(url, "blocked", error_message="Blocked by robots.txt")
        return

    try:
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
                            f"⚠️ Response too large ({content_length} bytes): {url}"
                        )
                        history.log_crawl_attempt(
                            url,
                            "skipped",
                            resp.status,
                            f"Response too large: {content_length} bytes",
                        )
                        return
                except ValueError:
                    pass

            if resp.status == 200 and ("text/html" in ct or "application/xhtml" in ct):
                # Read with size limit
                body = await resp.content.read(MAX_RESPONSE_SIZE)
                if len(body) >= MAX_RESPONSE_SIZE:
                    logger.warning(
                        f"⚠️ Response truncated at {MAX_RESPONSE_SIZE} bytes: {url}"
                    )
                    history.log_crawl_attempt(
                        url,
                        "skipped",
                        resp.status,
                        f"Response truncated at {MAX_RESPONSE_SIZE} bytes",
                    )
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
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None, lambda: clear_retry_count(redis_client, url)
                        )
                        history.log_crawl_attempt(url, "indexed", 200)
                    else:
                        history.log_crawl_attempt(
                            url, "indexer_error", 500, "Indexer API rejected"
                        )
                else:
                    history.log_crawl_attempt(
                        url, "skipped", 200, "No main content found"
                    )

                # 5. Extract & Enqueue Links
                discovered = await loop.run_in_executor(None, extract_links, url, html)

                if discovered:
                    # Limit outlinks
                    discovered = discovered[:50]  # Max 50 links per page
                    await loop.run_in_executor(
                        None,
                        lambda: enqueue_batch(
                            redis_client,
                            discovered,
                            parent_score=score,
                            score_calculator=calculate_url_score,  # Use domain logic
                            queue_key=settings.CRAWL_QUEUE_KEY,
                            seen_key=settings.CRAWL_SEEN_KEY,
                        ),
                    )
                    logger.debug(f"📤 Enqueued {len(discovered)} links from {url}")

            elif resp.status in (429, 500, 502, 503, 504):
                # Retryable errors - check retry count
                logger.warning(f"⚠️ Retryable error {resp.status} for {url}")

                loop = asyncio.get_running_loop()
                retry_count = await loop.run_in_executor(
                    None, lambda: increment_retry_count(redis_client, url)
                )

                if retry_count >= MAX_RETRIES:
                    # Move to dead letter queue
                    logger.warning(
                        f"💀 Moving to dead letter after {retry_count} retries: {url}"
                    )
                    await loop.run_in_executor(
                        None,
                        lambda: move_to_dead_letter(
                            redis_client,
                            url,
                            f"HTTP {resp.status} after {retry_count} retries",
                        ),
                    )
                    history.log_crawl_attempt(
                        url,
                        "dead_letter",
                        resp.status,
                        f"Max retries ({MAX_RETRIES}) exceeded",
                    )
                else:
                    # Re-enqueue with lower priority
                    history.log_crawl_attempt(
                        url,
                        "retry_later",
                        resp.status,
                        f"Server error (retry {retry_count}/{MAX_RETRIES})",
                    )
                    await loop.run_in_executor(
                        None,
                        lambda: redis_client.zadd(
                            settings.CRAWL_QUEUE_KEY, {url: max(score - 5.0, -100.0)}
                        ),
                    )
            else:
                # Other HTTP errors (404, etc)
                logger.warning(f"❌ HTTP error {resp.status} for {url}")
                history.log_crawl_attempt(url, "http_error", resp.status, "HTTP Error")

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(f"🌐 Network error for {url}: {e}")

        # Check retry count
        loop = asyncio.get_running_loop()
        retry_count = await loop.run_in_executor(
            None, lambda: increment_retry_count(redis_client, url)
        )

        if retry_count >= MAX_RETRIES:
            # Move to dead letter queue
            logger.warning(
                f"💀 Moving to dead letter after {retry_count} network errors: {url}"
            )
            await loop.run_in_executor(
                None,
                lambda: move_to_dead_letter(
                    redis_client, url, f"Network error after {retry_count} retries"
                ),
            )
            history.log_crawl_attempt(
                url,
                "dead_letter",
                error_message=f"Max retries ({MAX_RETRIES}) exceeded: {e}",
            )
        else:
            # Re-enqueue with lower priority
            history.log_crawl_attempt(
                url,
                "network_error",
                error_message=f"{e} (retry {retry_count}/{MAX_RETRIES})",
            )
            await loop.run_in_executor(
                None,
                lambda: redis_client.zadd(
                    settings.CRAWL_QUEUE_KEY, {url: max(score - 5.0, -100.0)}
                ),
            )
    except Exception as e:
        logger.error(f"💥 Unexpected error processing {url}: {e}", exc_info=True)
        history.log_crawl_attempt(url, "unknown_error", error_message=str(e))


async def worker_loop(concurrency: int = 1):
    """
    Main crawler worker loop

    Args:
        concurrency: Number of concurrent crawl tasks

    Continuously dequeues URLs from Redis and processes them with concurrency control.
    """
    logger.info(f"🔄 Worker loop started with concurrency={concurrency}")

    # Initialize history database
    history.init_db()

    redis_client = get_redis()
    sem = asyncio.Semaphore(concurrency)  # Use provided concurrency

    connector = aiohttp.TCPConnector(
        limit_per_host=5,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )

    async with aiohttp.ClientSession(
        headers={"User-Agent": settings.CRAWL_USER_AGENT}, connector=connector
    ) as session:
        robots = AsyncRobotsCache(session, redis_client)

        logger.info(f"✅ Remote crawler started with concurrency={concurrency}")
        logger.info(f"📡 Submitting pages to: {settings.INDEXER_API_URL}")

        try:
            while True:
                # Dequeue next URL
                loop = asyncio.get_running_loop()
                item = await loop.run_in_executor(
                    None,
                    lambda: dequeue_top(
                        redis_client, queue_key=settings.CRAWL_QUEUE_KEY
                    ),
                )

                if not item:
                    # Queue is empty, wait before checking again
                    await asyncio.sleep(5)
                    continue

                url, score = item
                logger.info(f"📥 Processing: {url} (score={score:.1f})")

                # Process URL with semaphore concurrency control
                async def process_with_semaphore(url: str, score: float):
                    try:
                        await process_url(session, robots, redis_client, url, score)
                    finally:
                        sem.release()

                # Acquire semaphore for concurrency control
                await sem.acquire()

                # Create task for concurrent processing
                try:
                    asyncio.create_task(process_with_semaphore(url, score))
                except Exception as e:
                    # Release semaphore if task creation fails
                    sem.release()
                    logger.error(f"Failed to create task for {url}: {e}")

        except asyncio.CancelledError:
            logger.info("🛑 Worker loop cancelled")
            raise
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        except Exception as e:
            logger.error(f"💥 Worker loop error: {e}", exc_info=True)
            raise

    logger.info("🛑 Worker loop stopped")
