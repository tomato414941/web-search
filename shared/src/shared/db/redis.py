from typing import Iterable, Optional, cast
from urllib.parse import urlparse

import redis
from shared.core.infrastructure_config import settings


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def enqueue_if_new(
    r: redis.Redis, url: str, score: float, queue_key: str, seen_key: str
) -> bool:
    """
    Add URL to queue if not already seen (generic).

    Args:
        r: Redis client
        url: URL to enqueue
        score: Priority score
        queue_key: Redis sorted set key for queue
        seen_key: Redis set key for seen URLs

    Returns:
        True if URL was new and added, False if already seen
    """
    added = r.sadd(seen_key, url)
    if added == 1:
        r.zadd(queue_key, {url: float(score)})
        return True
    return False


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def enqueue_batch(
    r: redis.Redis,
    urls: Iterable[str],
    parent_score: float = 100.0,
    score_calculator=None,
    queue_key: str = "crawl:queue",  # Generic default
    seen_key: str = "crawl:seen",  # Generic default
) -> int:
    """
    Add multiple URLs to crawl queue (only new URLs).

    This is a generic infrastructure operation. URL scoring logic
    should be provided by the caller (application/domain layer).

    Args:
        r: Redis client
        urls: URLs to enqueue
        parent_score: Base score for URL prioritization
        score_calculator: Optional function(url, parent_score, visits) -> score
                         If None, uses simple parent_score * 0.9
        queue_key: Redis sorted set key for queue
        seen_key: Redis set key for seen URLs

    Returns:
        Number of URLs successfully added (excludes duplicates)
    """
    n = 0
    pipe = r.pipeline()
    for u in urls:
        pipe.sadd(seen_key, u)
    results = pipe.execute()

    # Filter new URLs
    to_add = [u for u, added in zip(urls, results) if added == 1]

    if to_add:
        # Get current domain counts
        pipe = r.pipeline()
        for u in to_add:
            d = get_domain(u)
            if d:
                # Increment and return new value
                pipe.zincrby("crawl:domains", 1.0, d)
            else:
                pipe.echo("noop")  # Dummy to keep index alignment

        domain_counts = pipe.execute()

        # Add to Queue with calculated score
        pipe = r.pipeline()
        for i, u in enumerate(to_add):
            # Calculate score
            if score_calculator:
                # Use provided scoring function (domain logic)
                d = get_domain(u)
                visits = 0
                if d:
                    try:
                        visits = int(float(domain_counts[i] or 0))
                    except (ValueError, TypeError):
                        visits = 0
                score = score_calculator(u, parent_score, visits)
            else:
                # Simple default: just use parent score with decay
                score = parent_score * 0.9

            pipe.zadd(queue_key, {u: score})

        pipe.execute()
        n = len(to_add)
    return n


def dequeue_top(
    r: redis.Redis, queue_key: str = "crawl:queue"
) -> Optional[tuple[str, float]]:
    """
    Remove and return highest-priority item from queue (generic).

    Args:
        r: Redis client
        queue_key: Redis sorted set key for queue

    Returns:
        Tuple of (url, score) or None if queue is empty
    """
    res = cast(list[tuple[str, float]], r.zpopmax(queue_key, 1))
    if not res:
        return None
    url, score = res[0]
    return url, float(score)


# --- Retry Management ---

MAX_RETRIES = 3
RETRY_KEY_PREFIX = "crawl:retry:"
DEAD_LETTER_KEY = "crawl:dead_letter"


def increment_retry_count(r: redis.Redis, url: str) -> int:
    """
    Increment retry count for a URL.

    Args:
        r: Redis client
        url: URL to track

    Returns:
        New retry count
    """
    key = f"{RETRY_KEY_PREFIX}{url}"
    count = r.incr(key)
    # Set TTL of 7 days for retry counter
    r.expire(key, 604800)
    return count


def get_retry_count(r: redis.Redis, url: str) -> int:
    """Get current retry count for a URL."""
    key = f"{RETRY_KEY_PREFIX}{url}"
    val = r.get(key)
    return int(val) if val else 0


def clear_retry_count(r: redis.Redis, url: str) -> None:
    """Clear retry count for a URL (after successful processing)."""
    key = f"{RETRY_KEY_PREFIX}{url}"
    r.delete(key)


def move_to_dead_letter(
    r: redis.Redis, url: str, reason: str = "", dead_letter_key: str = DEAD_LETTER_KEY
) -> None:
    """
    Move a URL to the dead letter queue.

    Args:
        r: Redis client
        url: URL to move
        reason: Reason for moving to dead letter
        dead_letter_key: Redis sorted set key for dead letter queue
    """
    import time

    # Store with timestamp as score for ordering
    r.zadd(dead_letter_key, {url: time.time()})
    # Clear retry counter
    clear_retry_count(r, url)


def should_move_to_dead_letter(r: redis.Redis, url: str) -> bool:
    """Check if URL should be moved to dead letter queue based on retry count."""
    return get_retry_count(r, url) >= MAX_RETRIES
