"""
Frontier Service

Manages manual URL admission and frontier inspection using UrlStore.
"""

import logging

from web_search_crawler.core.config import settings
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.db.url_store import UrlStore
from web_search_crawler.db.url_types import get_domain
from web_search_core.utils import MAX_URL_LENGTH, is_private_ip

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
        )
    return _url_store


class FrontierService:
    """Manual frontier admission and inspection service."""

    def __init__(self, url_store: UrlStore | None = None):
        self.url_store = url_store or _get_url_store()

    async def admit_urls(self, urls: list[str]) -> int:
        """
        Admit URLs into the crawl frontier.

        Args:
            urls: List of URLs to add

        Returns:
            Number of URLs admitted (excludes duplicates and recently crawled)
        """
        if not urls:
            return 0

        valid = []
        for url in urls:
            if len(url) > MAX_URL_LENGTH:
                continue
            domain = get_domain(url)
            if is_private_ip(domain):
                logger.warning("SSRF blocked at frontier admission: %s", url)
                continue
            valid.append(url)

        count = await run_in_db_executor(
            self.url_store.discover_and_admit_urls,
            valid,
            discovered_via="manual",
        )
        logger.info("Admitted %d/%d URLs into frontier", count, len(urls))
        return count

    def get_frontier_summary(self) -> dict:
        """
        Get frontier summary statistics.

        Returns:
            Dict with pending frontier depth and discovered URL count
        """
        stats = self.url_store.get_stats()

        return {
            "pending": stats["pending"],
            "total_seen": stats["total"],
        }

    def get_frontier_items(self, limit: int = 20) -> list[dict]:
        """
        Peek pending frontier items.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of dicts with URL info
        """
        items = self.url_store.peek(limit)
        return [{"url": item.url} for item in items]
