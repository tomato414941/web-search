"""Crawl task planner."""

from dataclasses import dataclass

from web_search_crawler.core.crawl_denylist import is_domain_denied
from web_search_crawler.db.crawler_runtime_store import CrawlerRuntimeStore
from web_search_crawler.db.url_types import CrawlTask


@dataclass
class CrawlTaskPlannerConfig:
    # Maximum concurrent requests per domain
    domain_max_concurrent: int = 2


class CrawlTaskPlanner:
    """
    Crawl task selector used by worker execution paths.

    Pops crawl tasks from CrawlerRuntimeStore and filters them against the current
    denied-domain and temporarily blocked-domain sets.
    """

    def __init__(
        self,
        url_store: CrawlerRuntimeStore,
        config: CrawlTaskPlannerConfig | None = None,
    ):
        self.url_store = url_store
        self.config = config or CrawlTaskPlannerConfig()
        self._denied_domains: frozenset[str] = frozenset()
        self._blocked_domains: frozenset[str] = frozenset()

    def _pop_plannable_items(self, count: int) -> list[CrawlTask]:
        return self.url_store.pop_ready_crawl_tasks(
            count,
            max_per_domain=self.config.domain_max_concurrent,
        )

    def set_denied_domains(self, domains: frozenset[str]) -> None:
        """Update the static crawler denylist."""
        self._denied_domains = domains

    def set_temporarily_blocked_domains(self, domains: frozenset[str]) -> None:
        """Update the temporary robots-blocked domains."""
        self._blocked_domains = domains

    def pop_ready_urls(self, count: int) -> list[CrawlTask]:
        """
        Pop multiple URLs that are ready to crawl.

        Args:
            count: Maximum number of crawl tasks to lease

        Returns:
            List of CrawlTasks ready for crawling
        """
        if count <= 0:
            return []

        items = self._pop_plannable_items(count)
        denied = self._denied_domains
        blocked = self._blocked_domains
        return [
            item
            for item in items
            if not (denied and is_domain_denied(item.domain, denied))
            and not (blocked and is_domain_denied(item.domain, blocked))
        ]
