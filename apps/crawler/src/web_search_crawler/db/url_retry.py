"""Frontier retry operations used by worker flows."""

from web_search_crawler.db.url_types import get_domain


class UrlRetryMixin:
    """Frontier retry operations."""

    db_path: str

    def requeue(self, url: str) -> bool:
        """Release a leased frontier URL back to pending for retry."""
        entry = self.get_frontier_entry(url)
        if entry is None or entry.status != "leased":
            return False
        released = self.release_frontier_urls([url], prefer_earlier=True)
        domain = get_domain(url)
        if released > 0 and hasattr(self, "domain_scheduling_state"):
            self.domain_scheduling_state.record_domain_retry(
                domain,
                default_delay_sec=1.0,
            )
        return released > 0
