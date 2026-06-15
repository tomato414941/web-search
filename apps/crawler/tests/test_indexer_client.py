"""
Indexer Client Tests

Tests for submit_page_to_indexer API client.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from web_search_crawler.services.indexer import submit_page_to_indexer


@pytest.mark.asyncio
async def test_submit_page_success():
    """Test successful page submission to indexer"""
    mock_response = AsyncMock()
    mock_response.status = 200

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_response

    result = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8000/documents",
        "test-api-key",
        "http://example.com/test",
        "Test Page",
        "Test content",
    )

    assert result.ok is True
    assert result.status_code == 200

    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args[1]
    assert call_kwargs["headers"]["X-API-Key"] == "test-api-key"
    assert call_kwargs["headers"]["Content-Type"] == "application/json"
    assert call_kwargs["json"]["url"] == "http://example.com/test"
    assert call_kwargs["json"]["title"] == "Test Page"
    assert call_kwargs["json"]["content"] == "Test content"


@pytest.mark.asyncio
async def test_submit_page_indexer_error():
    """Test indexer returns error (4xx/5xx)"""
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value='{"detail":"Indexing failed"}')

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_response

    result = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8000/documents",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert result.ok is False
    assert result.status_code == 500
    assert result.detail is not None
    assert "Indexing failed" in result.detail


@pytest.mark.asyncio
async def test_submit_page_network_error():
    """Test network error during submission"""
    mock_session = MagicMock()
    mock_session.post.side_effect = Exception("Connection refused")

    result = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8000/documents",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert result.ok is False
    assert result.status_code is None
    assert result.detail is not None
    assert "Connection refused" in result.detail


@pytest.mark.asyncio
async def test_submit_page_network_error_without_message():
    """Blank exceptions should still record the exception type."""

    class SilentError(Exception):
        def __str__(self) -> str:
            return ""

    mock_session = MagicMock()
    mock_session.post.side_effect = SilentError()

    result = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8000/documents",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert result.ok is False
    assert result.status_code is None
    assert result.detail == "Indexer request failed: SilentError"


@pytest.mark.asyncio
async def test_submit_page_timeout_fails_fast():
    """Timeout should fail fast without crawler-side retry."""
    mock_session = MagicMock()
    mock_session.post.side_effect = asyncio.TimeoutError()

    result = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8000/documents",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert result.ok is False
    assert result.detail is not None
    assert "TimeoutError" in result.detail
    assert mock_session.post.call_count == 1
