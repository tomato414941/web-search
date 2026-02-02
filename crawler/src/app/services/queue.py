"""
Queue Service

Manages Redis-based crawl queue operations.
"""

import logging

from shared.db.redis import enqueue_batch
from shared.db.seen_store import HybridSeenStore
from shared.db.search import get_connection
from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy-initialized seen store
_seen_store: HybridSeenStore | None = None


def _get_seen_store(redis_client) -> HybridSeenStore:
    """Get or create the HybridSeenStore instance."""
    global _seen_store
    if _seen_store is None:
        _seen_store = HybridSeenStore(
            redis_client=redis_client,
            db_path=settings.CRAWLER_DB_PATH,
            cache_ttl_days=settings.CRAWL_CACHE_TTL_DAYS,
            recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
        )
    return _seen_store


class QueueService:
    """Crawl queue management service"""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def enqueue_urls(self, urls: list[str], priority: float = 100.0) -> int:
        """
        Add URLs to crawl queue

        Args:
            urls: List of URLs to add
            priority: Priority score (higher = crawled sooner)

        Returns:
            Number of URLs added (excludes duplicates)
        """
        count = enqueue_batch(
            self.redis,
            urls,
            parent_score=priority,
            queue_key=settings.CRAWL_QUEUE_KEY,
            seen_key=settings.CRAWL_SEEN_KEY,
        )
        logger.info(f"Queued {count}/{len(urls)} URLs (priority={priority})")
        return count

    def get_stats(self) -> dict:
        """
        Get queue statistics

        Returns:
            Dict with queue_size, seen stats, and total_indexed
        """
        indexed_count = 0
        try:
            con = get_connection()
            cursor = con.execute(
                "SELECT COUNT(*) FROM crawl_history WHERE status IN ('success', 'indexed')"
            )
            indexed_count = cursor.fetchone()[0]
            con.close()
        except Exception as e:
            logger.warning(f"Failed to get indexed count: {e}")

        # Get seen URL stats from HybridSeenStore
        seen_store = _get_seen_store(self.redis)
        seen_stats = seen_store.get_stats()

        return {
            "queue_size": self.redis.zcard(settings.CRAWL_QUEUE_KEY),
            "total_seen": seen_stats["total_seen"],
            "active_seen": seen_stats["active_seen"],
            "cache_size": seen_stats["cache_size"],
            "total_indexed": indexed_count,
            # Legacy field for backward compatibility
            "total_crawled": seen_stats["active_seen"],
        }
