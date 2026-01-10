"""
Integration Tests

End-to-end tests for the full crawler workflow.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.workers.tasks import process_url


@pytest.mark.asyncio
async def test_process_url_success_flow():
    """Test complete process_url flow with successful indexing"""
    # Mock dependencies
    mock_session = MagicMock()

    # Mock robots check
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True

    # Mock Redis client
    mock_redis = MagicMock()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.text.return_value = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <p>Test content</p>
            <a href="/link1">Link 1</a>
            <a href="/link2">Link 2</a>
        </body>
        </html>
    """
    mock_session.get.return_value.__aenter__.return_value = mock_response

    # Mock html_to_doc to return parsed content
    with patch(
        "app.workers.tasks.html_to_doc", return_value=("Test Page", "Test content")
    ):
        # Mock extract_links
        with patch(
            "app.workers.tasks.extract_links", return_value=["http://example.com/link1"]
        ):
            # Mock indexer submission
            with patch(
                "app.workers.tasks.submit_page_to_indexer", new_callable=AsyncMock
            ) as mock_indexer:
                with patch(
                    "app.workers.tasks.history.log_crawl_attempt"
                ) as mock_history:
                    mock_indexer.return_value = True

                    # Execute
                    await process_url(
                        mock_session,
                        mock_robots,
                        mock_redis,
                        "http://example.com/test",
                        100.0,
                    )

                    # Verify robots check
                    mock_robots.can_fetch.assert_called_once()

                    # Verify HTTP fetch
                    mock_session.get.assert_called_once()

                    # Verify indexer submission
                    mock_indexer.assert_called_once()
                    call_args = mock_indexer.call_args[0]
                    assert call_args[3] == "http://example.com/test"  # URL
                    assert call_args[4] == "Test Page"  # Title
                    assert "Test content" in call_args[5]  # Content

                    # Verify history logging
                    mock_history.assert_called()
                    history_call = mock_history.call_args[0]
                    assert history_call[0] == "http://example.com/test"
                    assert history_call[1] == "indexed"


@pytest.mark.asyncio
async def test_process_url_robots_blocked():
    """Test process_url when robots.txt blocks URL"""
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = False  # Blocked
    mock_redis = MagicMock()

    with patch("app.workers.tasks.history.log_crawl_attempt") as mock_history:
        await process_url(
            mock_session, mock_robots, mock_redis, "http://example.com/blocked", 100.0
        )

        # Should not fetch
        mock_session.get.assert_not_called()

        # Should log as blocked
        mock_history.assert_called_once()
        assert mock_history.call_args[0][1] == "blocked"


@pytest.mark.asyncio
async def test_process_url_http_error():
    """Test process_url with HTTP error (404)"""
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_redis = MagicMock()

    # Mock 404 response with proper headers
    mock_response = AsyncMock()
    mock_response.status = 404
    mock_response.headers = {"Content-Type": "text/html"}  # Add header
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch("app.workers.tasks.history.log_crawl_attempt") as mock_history:
        await process_url(
            mock_session, mock_robots, mock_redis, "http://example.com/notfound", 100.0
        )

        # Should log as http_error
        mock_history.assert_called_once()
        assert mock_history.call_args[0][1] == "http_error"
        assert mock_history.call_args[0][2] == 404


@pytest.mark.asyncio
async def test_process_url_network_error():
    """Test process_url with network error"""
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_redis = MagicMock()

    # Mock network error
    import aiohttp

    mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

    with patch("app.workers.tasks.history.log_crawl_attempt") as mock_history:
        await process_url(
            mock_session, mock_robots, mock_redis, "http://example.com/error", 100.0
        )

        # Should log as network_error
        mock_history.assert_called_once()
        assert mock_history.call_args[0][1] == "network_error"


@pytest.mark.asyncio
async def test_process_url_indexer_failure():
    """Test process_url when indexer rejects page"""
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_redis = MagicMock()

    # Mock successful HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.text.return_value = "<html><body>Test</body></html>"
    mock_session.get.return_value.__aenter__.return_value = mock_response

    # Mock html_to_doc to return content
    with patch("app.workers.tasks.html_to_doc", return_value=("Test", "Test content")):
        # Mock extract_links
        with patch("app.workers.tasks.extract_links", return_value=[]):
            # Mock indexer failure
            with patch(
                "app.workers.tasks.submit_page_to_indexer", new_callable=AsyncMock
            ) as mock_indexer:
                with patch(
                    "app.workers.tasks.history.log_crawl_attempt"
                ) as mock_history:
                    mock_indexer.return_value = False  # Indexer rejected

                    await process_url(
                        mock_session,
                        mock_robots,
                        mock_redis,
                        "http://example.com/test",
                        100.0,
                    )

                    # Should log as indexer_error
                    assert any(
                        call[0][1] == "indexer_error"
                        for call in mock_history.call_args_list
                    )


@pytest.mark.asyncio
async def test_process_url_retryable_error():
    """Test process_url with retryable HTTP error (503)"""
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_redis = MagicMock()

    # Mock 503 response with proper headers
    mock_response = AsyncMock()
    mock_response.status = 503
    mock_response.headers = {"Content-Type": "text/html"}  # Add header
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch("app.workers.tasks.history.log_crawl_attempt") as mock_history:
        await process_url(
            mock_session,
            mock_robots,
            mock_redis,
            "http://example.com/temp-error",
            100.0,
        )

        # Should log as retry_later
        mock_history.assert_called_once()
        assert mock_history.call_args[0][1] == "retry_later"

        # Should re-enqueue with lower priority
        mock_redis.zadd.assert_called_once()
