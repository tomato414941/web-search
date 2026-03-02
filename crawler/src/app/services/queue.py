"""
Queue Service

Manages crawl queue operations using UrlStore.
"""

import logging

from app.db.executor import run_in_db_executor
from app.db.url_store import UrlStore, get_domain
from app.core.config import settings
from app.domain.scoring import MANUAL_CRAWL_BOOST, get_domain_rank, seed_score
from shared.core.utils import is_private_ip

logger = logging.getLogger(__name__)

# Lazy-initialized instance
_url_store: UrlStore | None = None


def _get_url_store() -> UrlStore:
    """Get or create UrlStore instance."""
    global _url_store
    if _url_store is None:
        _url_store = UrlStore(
            settings.CRAWLER_DB_PATH,
            recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
            max_pending_per_domain=settings.MAX_PENDING_PER_DOMAIN,
        )
    return _url_store


class QueueService:
    """Crawl queue management service"""

    def __init__(self, url_store: UrlStore | None = None):
        self.url_store = url_store or _get_url_store()

    async def enqueue_urls(self, urls: list[str]) -> int:
        """
        Add URLs to crawl queue with manual-crawl priority.

        Each URL's score is based on its domain_rank + MANUAL_CRAWL_BOOST,
        capped at 100.

        Args:
            urls: List of URLs to add

        Returns:
            Number of URLs added (excludes duplicates and recently crawled)
        """
        if not urls:
            return 0

        scored = []
        for url in urls:
            domain = get_domain(url)
            if is_private_ip(domain):
                logger.warning("SSRF blocked at enqueue: %s", url)
                continue
            dr = get_domain_rank(domain)
            scored.append(
                (url, seed_score(domain_pagerank=dr, boost=MANUAL_CRAWL_BOOST))
            )

        count = await run_in_db_executor(self.url_store.add_batch_scored, scored)
        logger.info(f"Queued {count}/{len(urls)} URLs (manual crawl)")
        return count

    def get_stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dict with queue_size, history stats, and total_indexed
        """
        stats = self.url_store.get_stats()

        return {
            "queue_size": stats["pending"],
            "total_seen": stats["total"],
            "active_seen": stats["recent"],
            "total_indexed": stats["done"],
        }

    def get_queue_items(self, limit: int = 20) -> list[dict]:
        """
        Get top items from queue.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of dicts with url and score
        """
        items = self.url_store.peek(limit)
        return [{"url": item.url, "score": item.priority} for item in items]
