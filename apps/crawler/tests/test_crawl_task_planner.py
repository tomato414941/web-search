"""Crawl task planner tests."""

from unittest.mock import MagicMock

from web_search_crawler.crawl_task_planner import (
    CrawlTaskPlanner,
    CrawlTaskPlannerConfig,
)
from web_search_crawler.db.url_types import CrawlTask


class TestCrawlTaskPlannerBehavior:
    def _make_item(self, url, domain):
        return CrawlTask(url=url, domain=domain, created_at=0)

    def test_pops_ready_urls(self):
        items = [
            self._make_item("http://a.com/1", "a.com"),
            self._make_item("http://b.com/1", "b.com"),
        ]
        url_store = MagicMock()
        url_store.pop_ready_crawl_tasks.return_value = items
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())

        result = planner.pop_ready_urls(2)

        assert result == items
        url_store.pop_ready_crawl_tasks.assert_called_once_with(
            2,
            max_per_domain=2,
        )

    def test_zero_count_returns_empty(self):
        url_store = MagicMock()
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())

        assert planner.pop_ready_urls(0) == []
        url_store.pop_ready_crawl_tasks.assert_not_called()

    def test_temporarily_blocked_domains_are_dropped_after_pop(self):
        blocked_item = self._make_item("http://t.co/abc", "t.co")
        good_item = self._make_item("http://example.com/1", "example.com")
        url_store = MagicMock()
        url_store.pop_ready_crawl_tasks.return_value = [blocked_item, good_item]
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())
        planner.set_temporarily_blocked_domains(frozenset({"t.co"}))

        result = planner.pop_ready_urls(2)

        assert result == [good_item]

    def test_denied_domains_are_dropped_after_pop(self):
        denied_item = self._make_item(
            "http://accounts.example.com/1", "accounts.example.com"
        )
        good_item = self._make_item("http://example.com/1", "example.com")
        url_store = MagicMock()
        url_store.pop_ready_crawl_tasks.return_value = [denied_item, good_item]
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())
        planner.set_denied_domains(frozenset({"accounts.example.com"}))

        result = planner.pop_ready_urls(2)

        assert result == [good_item]
