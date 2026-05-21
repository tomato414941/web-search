"""
Frontier planner.

Leases frontier batches and keeps a small in-memory buffer for denied or
temporarily blocked domains. Durable host throttling lives in `domain_state`.
"""

from dataclasses import dataclass

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.db.url_store import UrlStore
from web_search_crawler.db.url_types import UrlItem


@dataclass
class FrontierPlannerConfig:
    # Maximum concurrent requests per domain
    domain_max_concurrent: int = 2
    # How many URLs to fetch from url_store at once
    batch_size: int = 100
    # Lease duration for durable frontier entries
    lease_seconds: int = 300


class FrontierPlanner:
    """
    Frontier batch selector used by worker execution paths.

    Leases frontier entries from UrlStore and filters them against the current
    denied-domain and temporarily blocked-domain sets.
    """

    def __init__(
        self,
        url_store: UrlStore,
        config: FrontierPlannerConfig | None = None,
    ):
        self.url_store = url_store
        self.config = config or FrontierPlannerConfig()
        self._buffer: list[UrlItem] = []
        self._denied_domains: frozenset[str] = frozenset()
        self._denied_version: int = 0
        self._blocked_domains: frozenset[str] = frozenset()
        self._blocked_version: int = 0
        self._purged_version: int = 0

    def _pop_plannable_batch(self, count: int) -> list[UrlItem]:
        fetch_count = max(count, self.config.batch_size)
        return self.url_store.pop_frontier_batch(
            fetch_count,
            max_per_domain=self.config.domain_max_concurrent,
            lease_seconds=self.config.lease_seconds,
        )

    def _return_blocked_items(self, items: list[UrlItem]) -> None:
        if not items:
            return
        self.url_store.release_frontier_urls([item.url for item in items])

    def set_denied_domains(self, domains: frozenset[str]) -> None:
        """Update the static crawler denylist."""
        if domains != self._denied_domains:
            self._denied_domains = domains
            self._denied_version += 1

    def set_temporarily_blocked_domains(self, domains: frozenset[str]) -> None:
        """Update the temporary robots-blocked domains."""
        if domains != self._blocked_domains:
            self._blocked_domains = domains
            self._blocked_version += 1

    def _is_denied(self, domain: str) -> bool:
        return is_domain_denied(domain, self._denied_domains)

    def _purge_denied_from_buffer(self) -> None:
        current_version = max(self._purged_version, 0)
        latest_version = self._denied_version
        if current_version == latest_version:
            return
        self._purged_version = latest_version
        if not self._denied_domains:
            return
        self._buffer = [
            item for item in self._buffer if not self._is_denied(item.domain)
        ]

    def lease_ready_urls(self, count: int) -> list[UrlItem]:
        """
        Lease multiple URLs that are ready to crawl.

        Args:
            count: Maximum number of frontier entries to lease

        Returns:
            List of leased UrlItems ready for crawling
        """
        if count <= 0:
            return []

        self._purge_denied_from_buffer()

        result = []
        to_remove = []

        denied = self._denied_domains
        blocked = self._blocked_domains

        def _can_select(domain: str) -> bool:
            if denied and is_domain_denied(domain, denied):
                return False
            if blocked and is_domain_denied(domain, blocked):
                return False
            return True

        denied_indices: list[int] = []
        for i, item in enumerate(self._buffer):
            if len(result) >= count:
                break
            if denied and is_domain_denied(item.domain, denied):
                denied_indices.append(i)
                continue
            if blocked and is_domain_denied(item.domain, blocked):
                continue
            if _can_select(item.domain):
                result.append(item)
                to_remove.append(i)

        for i in reversed(sorted(to_remove + denied_indices)):
            self._buffer.pop(i)

        while len(result) < count:
            fetch_count = count - len(result)
            items = self._pop_plannable_batch(fetch_count)
            if not items:
                break

            to_remove = []
            denied_idx: list[int] = []
            blocked_idx: list[int] = []
            for i, item in enumerate(items):
                if len(result) >= count:
                    break
                if denied and is_domain_denied(item.domain, denied):
                    denied_idx.append(i)
                    continue
                if blocked and is_domain_denied(item.domain, blocked):
                    blocked_idx.append(i)
                    continue
                if _can_select(item.domain):
                    result.append(item)
                    to_remove.append(i)

            if blocked_idx:
                self._return_blocked_items([items[i] for i in blocked_idx])

            skip_set = set(to_remove) | set(blocked_idx) | set(denied_idx)
            for i, item in enumerate(items):
                if i not in skip_set:
                    self._buffer.append(item)

        return result

    def buffer_size(self) -> int:
        """Return number of items in the local planner buffer."""
        return len(self._buffer)

    def stats(self) -> dict:
        """Get frontier planner statistics."""
        return {
            "buffer_size": len(self._buffer),
            "pending_count": self.url_store.pending_count(),
            "active_domains": 0,
            "backed_off_domains": 0,
        }
