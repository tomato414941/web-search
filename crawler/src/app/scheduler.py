"""
Scheduler - URL Selection with Rate Limiting

Decides which URLs to crawl next, respecting domain rate limits.
"""

import time
from dataclasses import dataclass
from typing import Optional

from app.core.blocklist import is_domain_blocked
from app.db.url_store import UrlStore
from app.db.url_types import UrlItem

# Maximum backoff in seconds (1 hour)
MAX_BACKOFF = 3600


@dataclass
class HostGate:
    next_fetch_at: float = 0.0
    inflight: int = 0
    min_interval: float = 1.0
    concurrency_limit: int = 2
    fail_streak: int = 0


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

        # Per-host rate limiting state
        self._gates: dict[str, HostGate] = {}

        # Buffer of URLs fetched from url_store but not yet ready
        self._buffer: list[UrlItem] = []

        # Combined blocked domains (static blocklist + dynamic robots-blocked)
        self._blocked_domains: frozenset[str] = frozenset()
        self._blocked_version: int = 0
        self._purged_version: int = 0

    def set_blocked_domains(self, domains: frozenset[str]) -> None:
        """Update the set of blocked domains (static + dynamic combined)."""
        if domains != self._blocked_domains:
            self._blocked_domains = domains
            self._blocked_version += 1

    def _get_gate(self, domain: str) -> HostGate:
        gate = self._gates.get(domain)
        if gate is None:
            gate = HostGate(
                min_interval=self.config.domain_min_interval,
                concurrency_limit=self.config.domain_max_concurrent,
            )
            self._gates[domain] = gate
        return gate

    def _is_blocked(self, domain: str) -> bool:
        """Check if domain is in the blocked set."""
        return is_domain_blocked(domain, self._blocked_domains)

    def _purge_blocked_from_buffer(self) -> None:
        """Remove blocked domains from internal buffer (skips if unchanged)."""
        if self._purged_version == self._blocked_version:
            return
        self._purged_version = self._blocked_version
        if not self._blocked_domains:
            return
        self._buffer = [
            item for item in self._buffer if not self._is_blocked(item.domain)
        ]

    def get_next(self) -> Optional[UrlItem]:
        """
        Get next URL that is ready to crawl.

        Respects domain rate limits and returns None if no URL is ready.
        """
        self._purge_blocked_from_buffer()
        now = time.time()

        # Try buffer first
        for i, item in enumerate(self._buffer):
            if self._can_fetch(item.domain, now):
                self._buffer.pop(i)
                return item

        # Fetch more from url_store if buffer is empty or exhausted
        if len(self._buffer) < self.config.batch_size // 2:
            items = self.url_store.pop_batch(self.config.batch_size)
            blocked_items = [item for item in items if self._is_blocked(item.domain)]
            items = [item for item in items if not self._is_blocked(item.domain)]
            if blocked_items:
                self.url_store.release_urls([item.url for item in blocked_items])
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

        Tracks per-domain selection count to avoid exceeding concurrency_limit
        within a single batch.

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
        selected_per_domain: dict[str, int] = {}

        blocked = self._blocked_domains

        def _can_select(domain: str) -> bool:
            if blocked and is_domain_blocked(domain, blocked):
                return False
            gate = self._get_gate(domain)
            if now < gate.next_fetch_at:
                return False
            effective_inflight = gate.inflight + selected_per_domain.get(domain, 0)
            return effective_inflight < gate.concurrency_limit

        # Check buffer — collect selected AND blocked indices for removal
        blocked_indices: list[int] = []
        blocked_urls: list[str] = []
        for i, item in enumerate(self._buffer):
            if len(result) >= count:
                break
            if blocked and is_domain_blocked(item.domain, blocked):
                blocked_indices.append(i)
                blocked_urls.append(item.url)
                continue
            if _can_select(item.domain):
                result.append(item)
                to_remove.append(i)
                selected_per_domain[item.domain] = (
                    selected_per_domain.get(item.domain, 0) + 1
                )

        # Remove selected + blocked items from buffer (reverse order)
        for i in reversed(sorted(to_remove + blocked_indices)):
            self._buffer.pop(i)

        # Release blocked URLs back to DB
        if blocked_urls:
            self.url_store.release_urls(blocked_urls)

        # If we need more, fetch from url_store
        while len(result) < count:
            items = self.url_store.pop_batch(self.config.batch_size)
            if not items:
                break

            to_remove = []
            blocked_idx: list[int] = []
            for i, item in enumerate(items):
                if len(result) >= count:
                    break
                if blocked and is_domain_blocked(item.domain, blocked):
                    blocked_idx.append(i)
                    continue
                if _can_select(item.domain):
                    result.append(item)
                    to_remove.append(i)
                    selected_per_domain[item.domain] = (
                        selected_per_domain.get(item.domain, 0) + 1
                    )

            # Release blocked URLs back to DB
            if blocked_idx:
                self.url_store.release_urls(
                    [items[i].url for i in blocked_idx],
                )

            # Add remaining to buffer (skip blocked)
            skip_set = set(to_remove) | set(blocked_idx)
            for i, item in enumerate(items):
                if i not in skip_set:
                    self._buffer.append(item)

        return result

    def _can_fetch(self, domain: str, now: float) -> bool:
        """Check if domain can be fetched based on rate limits."""
        gate = self._get_gate(domain)
        if now < gate.next_fetch_at:
            return False
        if gate.inflight >= gate.concurrency_limit:
            return False
        return True

    def record_start(self, domain: str) -> None:
        """Record that a request to domain has started."""
        gate = self._get_gate(domain)
        gate.inflight += 1

    def record_complete(self, domain: str, *, success: bool = True) -> None:
        """Record that a request to domain has completed."""
        gate = self._get_gate(domain)
        gate.inflight = max(0, gate.inflight - 1)
        now = time.time()
        if success:
            gate.fail_streak = 0
            gate.next_fetch_at = now + gate.min_interval
        else:
            gate.fail_streak += 1
            backoff = min(gate.min_interval * (2**gate.fail_streak), MAX_BACKOFF)
            gate.next_fetch_at = now + backoff

    def set_crawl_delay(self, domain: str, delay: float) -> None:
        """Set crawl delay for a domain (only if greater than current min_interval)."""
        gate = self._get_gate(domain)
        if delay > gate.min_interval:
            gate.min_interval = delay

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
        now = time.time()
        return {
            "buffer_size": len(self._buffer),
            "pending_count": self.url_store.pending_count(),
            "active_domains": len(
                [d for d, g in self._gates.items() if g.inflight > 0]
            ),
            "backed_off_domains": len(
                [
                    d
                    for d, g in self._gates.items()
                    if g.fail_streak > 0 and now < g.next_fetch_at
                ]
            ),
            "domain_min_interval": self.config.domain_min_interval,
            "domain_max_concurrent": self.config.domain_max_concurrent,
        }
