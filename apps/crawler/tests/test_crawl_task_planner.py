"""Frontier planner tests."""

from unittest.mock import MagicMock

from web_search_crawler.db.url_types import CrawlTask
from web_search_crawler.crawl_task_planner import (
    CrawlTaskPlanner,
    CrawlTaskPlannerConfig,
)


class TestCrawlTaskPlannerBehavior:
    def _make_planner(self, buffer_items=None, **kwargs):
        url_store = MagicMock()
        url_store.lease_ready_crawl_tasks.return_value = []
        url_store.release_crawl_tasks.return_value = 0
        config = CrawlTaskPlannerConfig(**kwargs)
        planner = CrawlTaskPlanner(url_store, config)
        if buffer_items:
            planner._buffer = list(buffer_items)
        return planner

    def _make_item(self, url, domain):
        return CrawlTask(url=url, domain=domain, created_at=0)

    def test_returns_urls_from_different_domains(self):
        items = [
            self._make_item("http://a.com/1", "a.com"),
            self._make_item("http://b.com/1", "b.com"),
            self._make_item("http://c.com/1", "c.com"),
        ]
        planner = self._make_planner(buffer_items=items)

        result = planner.lease_ready_urls(3)

        assert len(result) == 3
        assert {item.domain for item in result} == {"a.com", "b.com", "c.com"}

    def test_fetches_from_frontier_batch(self):
        url_store = MagicMock()
        url_store.lease_ready_crawl_tasks.side_effect = [
            [
                self._make_item("http://a.com/1", "a.com"),
                self._make_item("http://b.com/1", "b.com"),
            ],
            [],
        ]
        url_store.release_crawl_tasks.return_value = 0
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())

        result = planner.lease_ready_urls(2)

        assert [item.url for item in result] == [
            "http://a.com/1",
            "http://b.com/1",
        ]
        url_store.lease_ready_crawl_tasks.assert_called_once_with(
            100,
            max_per_domain=2,
            lease_seconds=300,
        )

    def test_prefetches_with_configured_batch_size(self):
        url_store = MagicMock()
        url_store.lease_ready_crawl_tasks.side_effect = [
            [
                self._make_item("http://a.com/1", "a.com"),
                self._make_item("http://b.com/1", "b.com"),
                self._make_item("http://c.com/1", "c.com"),
            ],
            [],
        ]
        url_store.release_crawl_tasks.return_value = 0
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig(batch_size=32))

        result = planner.lease_ready_urls(2)

        assert [item.url for item in result] == [
            "http://a.com/1",
            "http://b.com/1",
        ]
        assert planner.buffer_size() == 1
        url_store.lease_ready_crawl_tasks.assert_called_once_with(
            32,
            max_per_domain=2,
            lease_seconds=300,
        )

    def test_zero_count_returns_empty(self):
        items = [self._make_item("http://a.com/1", "a.com")]
        planner = self._make_planner(buffer_items=items)

        assert planner.lease_ready_urls(0) == []
        assert planner.buffer_size() == 1

    def test_temporarily_blocked_domains_stay_buffered(self):
        items = [
            self._make_item("http://facebook.com/1", "facebook.com"),
            self._make_item("http://a.com/1", "a.com"),
            self._make_item("http://www.linkedin.com/1", "www.linkedin.com"),
            self._make_item("http://b.com/1", "b.com"),
        ]
        planner = self._make_planner(buffer_items=items)
        planner.set_temporarily_blocked_domains(
            frozenset({"facebook.com", "linkedin.com"})
        )

        result = planner.lease_ready_urls(4)

        assert len(result) == 2
        assert {item.domain for item in result} == {"a.com", "b.com"}
        assert planner.buffer_size() == 2

    def test_blocked_domains_from_frontier_batch_are_released(self):
        blocked_item = self._make_item("http://t.co/abc", "t.co")
        good_item = self._make_item("http://example.com/1", "example.com")
        url_store = MagicMock()
        url_store.lease_ready_crawl_tasks.side_effect = [[blocked_item, good_item], []]
        url_store.release_crawl_tasks.return_value = 1
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())
        planner.set_temporarily_blocked_domains(frozenset({"t.co"}))

        result = planner.lease_ready_urls(2)

        assert len(result) == 1
        assert result[0].domain == "example.com"
        assert planner.buffer_size() == 0
        url_store.release_crawl_tasks.assert_called_once_with(["http://t.co/abc"])

    def test_denied_domains_are_dropped_without_release(self):
        denied_item = self._make_item(
            "http://accounts.example.com/1", "accounts.example.com"
        )
        good_item = self._make_item("http://example.com/1", "example.com")
        url_store = MagicMock()
        url_store.lease_ready_crawl_tasks.side_effect = [[denied_item, good_item], []]
        url_store.release_crawl_tasks.return_value = 0
        planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())
        planner.set_denied_domains(frozenset({"accounts.example.com"}))

        result = planner.lease_ready_urls(2)

        assert len(result) == 1
        assert result[0].domain == "example.com"
        assert planner.buffer_size() == 0
        url_store.release_crawl_tasks.assert_not_called()
