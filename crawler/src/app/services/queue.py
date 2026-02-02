"""
Queue Service

Manages crawl queue operations using Frontier and History.
"""

import logging

from app.db import Frontier, History
from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy-initialized instances
_frontier: Frontier | None = None
_history: History | None = None


def _get_frontier() -> Frontier:
    """Get or create Frontier instance."""
    global _frontier
    if _frontier is None:
        _frontier = Frontier(settings.CRAWLER_DB_PATH)
    return _frontier


def _get_history() -> History:
    """Get or create History instance."""
    global _history
    if _history is None:
        _history = History(
            settings.CRAWLER_DB_PATH,
            recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
        )
    return _history


class QueueService:
    """Crawl queue management service"""

    def __init__(
        self, frontier: Frontier | None = None, history: History | None = None
    ):
        self.frontier = frontier or _get_frontier()
        self.history = history or _get_history()

    async def enqueue_urls(self, urls: list[str], priority: float = 100.0) -> int:
        """
        Add URLs to crawl queue.

        Args:
            urls: List of URLs to add
            priority: Priority score (higher = crawled sooner)

        Returns:
            Number of URLs added (excludes duplicates and recently crawled)
        """
        if not urls:
            return 0

        # Filter out recently crawled URLs
        new_urls = self.history.filter_new(urls)

        # Filter out URLs already in frontier
        new_urls = [u for u in new_urls if not self.frontier.contains(u)]

        if not new_urls:
            logger.info(f"All {len(urls)} URLs already seen or in queue")
            return 0

        # Add to frontier
        count = self.frontier.add_batch(new_urls, priority=priority)
        logger.info(f"Queued {count}/{len(urls)} URLs (priority={priority})")
        return count

    def get_stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dict with queue_size, history stats, and total_indexed
        """
        history_stats = self.history.get_stats()

        return {
            "queue_size": self.frontier.size(),
            "total_seen": history_stats["total"],
            "active_seen": history_stats["recent"],
            "cache_size": 0,  # No Redis cache anymore
            "total_indexed": history_stats["done"],
            # Legacy field for backward compatibility
            "total_crawled": history_stats["recent"],
        }

    def get_queue_items(self, limit: int = 20) -> list[dict]:
        """
        Get top items from queue.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of dicts with url and score
        """
        items = self.frontier.peek(limit)
        return [{"url": item.url, "score": item.priority} for item in items]
