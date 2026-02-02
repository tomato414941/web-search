"""
Redis Client

Provides Redis connection for services that still need it.
Note: Crawler no longer uses Redis for URL queue management.
"""

import redis
from shared.core.infrastructure_config import settings


def get_redis() -> redis.Redis:
    """Get a Redis client connection."""
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
