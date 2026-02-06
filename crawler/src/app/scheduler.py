"""
Scheduler - URL Selection with Rate Limiting

Decides which URLs to crawl next, respecting domain rate limits.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from app.db.url_store import UrlStore, UrlItem


@dataclass
class SchedulerConfig:
    # Minimum seconds between requests to same domain
    domain_min_interval: float = 1.0
    # Maximum concurrent requests per domain
    domain_max_concurrent: int = 2
    # How many URLs to fetch from url_store at once
    batch_size: int = 100


class Scheduler:
    """
    URL Scheduler with domain rate limiting.

    Fetches URLs from UrlStore and applies domain-based rate limiting
    to avoid overloading individual hosts.
    """

    def __init__(
        self,
        url_store: UrlStore,
        config: Optional[SchedulerConfig] = None,
    ):
        self.url_store = url_store
        self.config = config or SchedulerConfig()

        # Track last request time per domain
        self._last_request: dict[str, float] = defaultdict(float)

        # Track concurrent requests per domain
        self._concurrent: dict[str, int] = defaultdict(int)

        # Buffer of URLs fetched from url_store but not yet ready
        self._buffer: list[UrlItem] = []

    def get_next(self) -> Optional[UrlItem]:
        """
        Get next URL that is ready to crawl.

        Respects domain rate limits and returns None if no URL is ready.
        """
        now = time.time()

        # Try buffer first
        for i, item in enumerate(self._buffer):
            if self._can_fetch(item.domain, now):
                self._buffer.pop(i)
                return item

        # Fetch more from url_store if buffer is empty or exhausted
        if len(self._buffer) < self.config.batch_size // 2:
            items = self.url_store.pop_batch(self.config.batch_size)
            self._buffer.extend(items)

        # Try again with new items
        for i, item in enumerate(self._buffer):
            if self._can_fetch(item.domain, now):
                self._buffer.pop(i)
                return item

        return None

    def get_ready_urls(self, count: int) -> list[UrlItem]:
        """
        Get multiple URLs that are ready to crawl.

        Args:
            count: Maximum number of URLs to return

        Returns:
            List of UrlItems that are ready for crawling
        """
        if count <= 0:
            return []

        now = time.time()
        result = []
        to_remove = []

        # Check buffer
        for i, item in enumerate(self._buffer):
            if len(result) >= count:
                break
            if self._can_fetch(item.domain, now):
                result.append(item)
                to_remove.append(i)

        # Remove selected items from buffer (reverse order to preserve indices)
        for i in reversed(to_remove):
            self._buffer.pop(i)

        # If we need more, fetch from url_store
        while len(result) < count:
            items = self.url_store.pop_batch(self.config.batch_size)
            if not items:
                break

            to_remove = []
            for i, item in enumerate(items):
                if len(result) >= count:
                    break
                if self._can_fetch(item.domain, now):
                    result.append(item)
                    to_remove.append(i)

            # Add remaining to buffer
            for i, item in enumerate(items):
                if i not in to_remove:
                    self._buffer.append(item)

        return result

    def _can_fetch(self, domain: str, now: float) -> bool:
        """Check if domain can be fetched based on rate limits."""
        # Check interval
        last = self._last_request.get(domain, 0)
        if now - last < self.config.domain_min_interval:
            return False

        # Check concurrent limit
        if self._concurrent.get(domain, 0) >= self.config.domain_max_concurrent:
            return False

        return True

    def record_start(self, domain: str) -> None:
        """Record that a request to domain has started."""
        self._concurrent[domain] = self._concurrent.get(domain, 0) + 1
        self._last_request[domain] = time.time()

    def record_complete(self, domain: str) -> None:
        """Record that a request to domain has completed."""
        self._concurrent[domain] = max(0, self._concurrent.get(domain, 0) - 1)

    def return_to_buffer(self, item: UrlItem) -> None:
        """
        Return an item to the buffer (e.g., if processing failed).

        The item will be tried again when rate limit allows.
        """
        self._buffer.insert(0, item)

    def buffer_size(self) -> int:
        """Return number of items in buffer."""
        return len(self._buffer)

    def stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "buffer_size": len(self._buffer),
            "pending_count": self.url_store.pending_count(),
            "active_domains": len([d for d, c in self._concurrent.items() if c > 0]),
            "domain_min_interval": self.config.domain_min_interval,
            "domain_max_concurrent": self.config.domain_max_concurrent,
        }
