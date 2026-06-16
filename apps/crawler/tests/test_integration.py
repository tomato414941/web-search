"""Integration tests for crawler runtime flows."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from web_search_core.urls import url_hash
from web_search_crawler.crawl_task_planner import (
    CrawlTaskPlanner,
    CrawlTaskPlannerConfig,
)
from web_search_crawler.db import CrawlerRuntimeStore
from web_search_crawler.db.connection import db_connection, db_transaction
from web_search_crawler.services.indexer import IndexerSubmitResult
from web_search_crawler.utils.parser import ParsedDocument
from web_search_crawler.workers.tasks import process_url
from web_search_web_model import LinkGraphRepository, UrlLedgerRepository


@pytest.fixture
def test_components(tmp_path):
    db_path = str(tmp_path / "test.db")
    url_store = CrawlerRuntimeStore(db_path, recrawl_after_days=30)
    url_ledger = UrlLedgerRepository(url_store.url_admission_policy)
    link_graph = LinkGraphRepository(url_store.url_admission_policy)
    planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())
    return url_store, url_ledger, link_graph, planner


def _record_url(url_store: CrawlerRuntimeStore, url: str) -> None:
    UrlLedgerRepository(url_store.url_admission_policy).record_discovered_url(url)


def _record_urls(url_store: CrawlerRuntimeStore, urls: list[str]) -> None:
    UrlLedgerRepository(url_store.url_admission_policy).record_discovered_urls(urls)


def _queue_contains(url_store: CrawlerRuntimeStore, url: str) -> bool:
    with db_connection(url_store.db_path) as cur:
        cur.execute(
            "SELECT 1 FROM crawl_queue WHERE url_hash = %s",
            (url_hash(url),),
        )
        return cur.fetchone() is not None


def _url_ledger_contains(url_store: CrawlerRuntimeStore, url: str) -> bool:
    with db_connection(url_store.db_path) as cur:
        cur.execute("SELECT 1 FROM urls WHERE url_hash = %s", (url_hash(url),))
        return cur.fetchone() is not None


def test_enqueue_url_for_crawl_adds_known_url_to_queue(test_url_store):
    url = "https://example.com/news"
    _record_url(test_url_store, url)

    assert test_url_store.enqueue_url_for_crawl(url) is True
    assert _queue_contains(test_url_store, url)


def test_enqueue_url_for_crawl_deduplicates_queue_rows(test_url_store):
    url = "https://example.com/news"
    _record_url(test_url_store, url)

    assert test_url_store.enqueue_url_for_crawl(url) is True
    assert test_url_store.enqueue_url_for_crawl(url) is False


def test_pop_ready_crawl_tasks_removes_queue_rows(test_url_store):
    urls = ["https://example.com/news", "https://example.org/blog"]
    _record_urls(test_url_store, urls)
    assert test_url_store.enqueue_urls_for_crawl(urls) == 2

    popped = test_url_store.pop_ready_crawl_tasks(2)

    assert {item.url for item in popped} == set(urls)
    assert all(not _queue_contains(test_url_store, url) for url in urls)


def test_pop_ready_crawl_tasks_respects_domain_backoff(test_url_store):
    blocked = "https://blocked.example.com/news"
    ready = "https://ready.example.com/news"
    _record_urls(test_url_store, [blocked, ready])
    test_url_store.enqueue_urls_for_crawl([blocked, ready])
    now = int(time.time())
    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE domain_state
            SET backoff_until = %s
            WHERE domain = %s
            """,
            (now + 3600, "blocked.example.com"),
        )

    popped = test_url_store.pop_ready_crawl_tasks(2)

    assert [item.url for item in popped] == [ready]
    assert _queue_contains(test_url_store, blocked)


def test_pop_ready_crawl_tasks_respects_max_per_domain(test_url_store):
    urls = [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
        "https://example.org/a",
    ]
    _record_urls(test_url_store, urls)
    test_url_store.enqueue_urls_for_crawl(urls)

    popped = test_url_store.pop_ready_crawl_tasks(4, max_per_domain=2)

    popped_by_domain: dict[str, int] = {}
    for item in popped:
        popped_by_domain[item.domain] = popped_by_domain.get(item.domain, 0) + 1
    assert popped_by_domain["example.com"] == 2
    assert popped_by_domain["example.org"] == 1


def test_purge_denied_domains_removes_matching_queue_rows(test_url_store):
    denied = "https://blocked.example.com/news"
    allowed = "https://allowed.example.com/news"
    _record_urls(test_url_store, [denied, allowed])
    test_url_store.enqueue_urls_for_crawl([denied, allowed])

    deleted = test_url_store.purge_denied_domains(frozenset({"blocked.example.com"}))

    assert deleted == 1
    assert not _queue_contains(test_url_store, denied)
    assert _queue_contains(test_url_store, allowed)


@pytest.mark.asyncio
async def test_process_url_success_flow(test_components):
    url_store, url_ledger, link_graph, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"""
        <html>
        <head><title>Test Page</title></head>
        <body><p>Test content</p><a href="/news">News</a></body>
        </html>
        """
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with (
        patch(
            "web_search_crawler.services.html_processing.parse_page",
            return_value=ParsedDocument(
                title="Test Page",
                content="Test content",
                outlinks=["http://example.com/news"],
            ),
        ),
        patch(
            "web_search_crawler.services.html_processing.submit_page_to_indexer",
            new_callable=AsyncMock,
        ) as mock_indexer,
        patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"),
    ):
        mock_indexer.return_value = IndexerSubmitResult(ok=True, status_code=200)

        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            "http://example.com/test",
        )

    mock_robots.can_fetch.assert_called_once()
    mock_session.get.assert_called_once()
    mock_indexer.assert_called_once()
    assert _url_ledger_contains(url_store, "http://example.com/test")


@pytest.mark.asyncio
async def test_process_url_network_error_does_not_enqueue_again(test_components):
    url_store, url_ledger, link_graph, planner = test_components
    test_url = "http://example.com/error"
    _record_url(url_store, test_url)
    url_store.enqueue_url_for_crawl(test_url)
    assert url_store.pop_ready_crawl_tasks(1)

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)
    mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

    with patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            test_url,
        )

    assert not _queue_contains(url_store, test_url)
