import math
from typing import Iterable, Optional, cast
from urllib.parse import urlparse

import redis
from shared.core.infrastructure_config import settings


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def enqueue_if_new(
    r: redis.Redis, 
    url: str, 
    score: float,
    queue_key: str,
    seen_key: str
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


def calculate_score(url: str, parent_score: float, domain_visits: int) -> float:
    """
    DEPRECATED: This function has been moved to crawler.domain.scoring.

    Please use app.domain.scoring.calculate_url_score() instead.
    This function will be removed in a future version.

    Calculate URL priority score based on:
    1. Parent Score (Inheritance)
    2. Domain Freshness (Log decay)
    3. URL Depth (Hierarchy)
    4. Path Keywords (Utility)
    """
    import warnings

    warnings.warn(
        "calculate_score() is deprecated. Use app.domain.scoring.calculate_url_score() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Keep implementation for backward compatibility
    # 1. Inheritance
    base = parent_score * 0.9

    # 2. Domain Freshness
    # 1st visit: 1.0, 10th: ~0.5, 100th: ~0.33
    domain_factor = 1.0 / (1.0 + math.log10(domain_visits + 1))

    # 3. URL Depth
    # Penalize deep hierarchy
    path = urlparse(url).path
    depth = max(0, path.count("/") - 1)
    depth_factor = 0.9**depth

    # 4. Path Keywords
    path_lower = path.lower()
    path_factor = 1.0
    if "list" in path_lower or "index" in path_lower or "category" in path_lower:
        path_factor = 1.2
    if (
        "login" in path_lower
        or "signup" in path_lower
        or "archive" in path_lower
        or "tag" in path_lower
    ):
        path_factor = 0.5

    return base * domain_factor * depth_factor * path_factor


def enqueue_batch(
    r: redis.Redis,
    urls: Iterable[str],
    parent_score: float = 100.0,
    score_calculator=None,
    queue_key: str = "crawl:queue",  # Generic default
    seen_key: str = "crawl:seen"      # Generic default
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
                pipe.do_nothing()  # Dummy to keep index alignment

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


def dequeue_top(r: redis.Redis, queue_key: str = "crawl:queue") -> Optional[tuple[str, float]]:
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
