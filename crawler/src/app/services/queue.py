"""
Queue Service

Manages Redis-based crawl queue operations.
"""

import logging
import sqlite3

from shared.db.redis import enqueue_batch
from app.core.config import settings
from app.utils.history import get_db_path

logger = logging.getLogger(__name__)


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
            Dict with queue_size, total_crawled, total_indexed (Crawler's domain model)
        """
        indexed_count = 0
        try:
            db_path = get_db_path()
            with sqlite3.connect(db_path) as con:
                cursor = con.execute(
                    "SELECT COUNT(*) FROM crawl_history WHERE status = 'success'"
                )
                indexed_count = cursor.fetchone()[0]
        except Exception as e:
            logger.warning(f"Failed to get indexed count: {e}")

        return {
            "queue_size": self.redis.zcard(settings.CRAWL_QUEUE_KEY),
            "total_crawled": self.redis.scard(settings.CRAWL_SEEN_KEY),
            "total_indexed": indexed_count,
        }
