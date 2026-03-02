"""
Integration Tests

End-to-end tests for the full crawler workflow.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.db import UrlStore
from app.services.indexer import IndexerSubmitResult
from app.scheduler import Scheduler, SchedulerConfig
from app.workers.tasks import process_url


@pytest.fixture
def test_components(tmp_path):
    """Create test UrlStore and Scheduler"""
    db_path = str(tmp_path / "test.db")
    url_store = UrlStore(db_path, recrawl_after_days=30)
    scheduler = Scheduler(url_store, SchedulerConfig())
    return url_store, scheduler


@pytest.mark.asyncio
async def test_process_url_success_flow(test_components):
    """Test complete process_url flow with successful indexing"""
    url_store, scheduler = test_components

    # Mock dependencies
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <p>Test content</p>
            <a href="/link1">Link 1</a>
        </body>
        </html>
    """
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch(
        "app.workers.pipeline.html_to_doc",
        return_value=("Test Page", "Test content", None),
    ):
        with patch(
            "app.workers.pipeline.extract_links",
            return_value=["http://example.com/link1"],
        ):
            with patch(
                "app.workers.pipeline.submit_page_to_indexer", new_callable=AsyncMock
            ) as mock_indexer:
                with patch("app.workers.tasks.history_log.log_crawl_attempt"):
                    mock_indexer.return_value = IndexerSubmitResult(
                        ok=True, status_code=202, job_id="job-1"
                    )

                    await process_url(
                        mock_session,
                        mock_robots,
                        url_store,
                        scheduler,
                        "http://example.com/test",
                        100.0,
                    )

                    # Verify robots check
                    mock_robots.can_fetch.assert_called_once()

                    # Verify HTTP fetch
                    mock_session.get.assert_called_once()

                    # Verify indexer submission
                    mock_indexer.assert_called_once()

                    # Verify URL was recorded as done
                    assert url_store.contains("http://example.com/test")


@pytest.mark.asyncio
async def test_process_url_robots_blocked(test_components):
    """Test process_url when robots.txt blocks URL"""
    url_store, scheduler = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = False  # Blocked
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    with patch("app.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            scheduler,
            "http://example.com/blocked",
            100.0,
        )

        # Should not fetch
        mock_session.get.assert_not_called()

        # URL should be recorded as failed
        assert url_store.contains("http://example.com/blocked")


@pytest.mark.asyncio
async def test_process_url_http_error(test_components):
    """Test process_url with HTTP error (404)"""
    url_store, scheduler = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock 404 response
    mock_response = AsyncMock()
    mock_response.status = 404
    mock_response.headers = {"Content-Type": "text/html"}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch("app.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            scheduler,
            "http://example.com/notfound",
            100.0,
        )

        # URL should be recorded as failed
        assert url_store.contains("http://example.com/notfound")


@pytest.mark.asyncio
async def test_process_url_network_error(test_components):
    """Test process_url with network error re-queues URL from crawling to pending."""
    url_store, scheduler = test_components
    test_url = "http://example.com/error"

    # Simulate real flow: URL is in crawling status before process_url runs
    url_store.add(test_url, 100.0)
    url_store.pop_batch(1)  # marks as crawling

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock network error
    import aiohttp

    mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

    with patch("app.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            scheduler,
            test_url,
            100.0,
        )

        # URL should be re-queued as pending (retry)
        stats = url_store.get_stats()
        assert stats["pending"] == 1
        assert stats["crawling"] == 0


@pytest.mark.asyncio
async def test_process_url_discovers_links(test_components):
    """Test that process_url adds discovered links to url_store"""
    url_store, scheduler = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"<html><body>Test</body></html>"
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch("app.workers.pipeline.html_to_doc", return_value=("Test", "Content", None)):
        with patch(
            "app.workers.pipeline.extract_links",
            return_value=[
                "http://example.com/link1",
                "http://example.com/link2",
            ],
        ):
            with patch(
                "app.workers.pipeline.submit_page_to_indexer", new_callable=AsyncMock
            ) as mock_indexer:
                with patch("app.workers.tasks.history_log.log_crawl_attempt"):
                    mock_indexer.return_value = IndexerSubmitResult(
                        ok=True, status_code=202, job_id="job-2"
                    )

                    await process_url(
                        mock_session,
                        mock_robots,
                        url_store,
                        scheduler,
                        "http://example.com/",
                        100.0,
                    )

                    # Discovered links should be in url_store
                    assert url_store.contains("http://example.com/link1")
                    assert url_store.contains("http://example.com/link2")


@pytest.mark.asyncio
async def test_process_url_non_html_200_logged_as_skipped(test_components):
    """Non-HTML 200 responses should be logged as skipped, not http_error."""
    url_store, scheduler = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/x-gzip"}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch("app.workers.pipeline.submit_page_to_indexer", new_callable=AsyncMock) as m:
        with patch("app.workers.tasks.history_log.log_crawl_attempt") as mock_log:
            await process_url(
                mock_session,
                mock_robots,
                url_store,
                scheduler,
                "http://example.com/archive.gz",
                100.0,
            )

    m.assert_not_called()
    mock_log.assert_called_once_with(
        "http://example.com/archive.gz",
        "skipped",
        200,
        "Non-HTML content-type: application/x-gzip",
    )
    assert url_store.contains("http://example.com/archive.gz")


@pytest.mark.asyncio
async def test_process_url_logs_indexer_error_detail(test_components):
    """Indexer error details should be persisted in crawl history."""
    url_store, scheduler = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"<html><head><title>T</title></head><body>C</body></html>"
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch(
        "app.workers.pipeline.html_to_doc",
        return_value=("T", "content", None),
    ):
        with patch("app.workers.pipeline.extract_links", return_value=[]):
            with patch(
                "app.workers.pipeline.submit_page_to_indexer", new_callable=AsyncMock
            ) as mock_indexer:
                with patch(
                    "app.workers.tasks.history_log.log_crawl_attempt"
                ) as mock_log:
                    mock_indexer.return_value = IndexerSubmitResult(
                        ok=False,
                        status_code=422,
                        detail="Indexer 422: url_too_long",
                    )
                    await process_url(
                        mock_session,
                        mock_robots,
                        url_store,
                        scheduler,
                        "http://example.com/fail",
                        100.0,
                    )

    mock_log.assert_any_call(
        "http://example.com/fail",
        "indexer_error",
        422,
        "Indexer 422: url_too_long",
    )
    assert url_store.contains("http://example.com/fail")


@pytest.mark.asyncio
async def test_process_url_retry_requeues_crawling_url(test_components):
    """Verify retry moves URL from crawling -> pending via requeue_for_retry."""
    url_store, scheduler = test_components
    test_url = "http://example.com/retry-test"

    # Pre-add and pop to set status to 'crawling'
    url_store.add(test_url, 50.0)
    popped = url_store.pop_batch(1)
    assert len(popped) == 1
    stats = url_store.get_stats()
    assert stats["crawling"] == 1
    assert stats["pending"] == 0

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock network error to trigger retry
    import aiohttp

    mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

    with patch("app.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            scheduler,
            test_url,
            50.0,
        )

    # URL should be back to pending (not stuck in crawling)
    stats = url_store.get_stats()
    assert stats["pending"] == 1, f"Expected pending=1, got {stats}"
    assert stats["crawling"] == 0, f"Expected crawling=0, got {stats}"


def test_requeue_for_retry_transitions_crawling_to_pending(tmp_path):
    """requeue_for_retry should move crawling -> pending."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    url_store.add("http://example.com/r", 50.0)
    url_store.pop_batch(1)  # marks as crawling

    result = url_store.requeue_for_retry("http://example.com/r", 45.0)
    assert result is True

    stats = url_store.get_stats()
    assert stats["pending"] == 1
    assert stats["crawling"] == 0


def test_requeue_for_retry_noop_if_not_crawling(tmp_path):
    """requeue_for_retry should be a no-op if URL is not in crawling status."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    url_store.add("http://example.com/noop", 50.0)

    # Status is 'pending', not 'crawling'
    result = url_store.requeue_for_retry("http://example.com/noop", 45.0)
    assert result is False


@pytest.mark.asyncio
async def test_process_url_too_long_is_skipped_before_fetch(test_components):
    """Overly long URLs should be skipped before robots/fetch/indexer."""
    from shared.core.utils import MAX_URL_LENGTH

    url_store, scheduler = test_components
    over_limit_url = "http://example.com/" + ("a" * MAX_URL_LENGTH)

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    with patch("app.workers.tasks.history_log.log_crawl_attempt") as mock_log:
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            scheduler,
            over_limit_url,
            100.0,
        )

    mock_robots.can_fetch.assert_not_called()
    mock_session.get.assert_not_called()
    assert mock_log.call_args.args[0] == over_limit_url
    assert mock_log.call_args.args[1] == "skipped"
    assert "URL too long:" in mock_log.call_args.kwargs["error_message"]
    assert url_store.contains(over_limit_url)
