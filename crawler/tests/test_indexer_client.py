"""
Indexer Client Tests

Tests for submit_page_to_indexer API client.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.indexer import submit_page_to_indexer


@pytest.mark.asyncio
async def test_submit_page_success():
    """Test successful page submission to indexer"""
    mock_response = AsyncMock()
    mock_response.status = 200

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_response

    success = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8080/api/indexer/page",
        "test-api-key",
        "http://example.com/test",
        "Test Page",
        "Test content",
    )

    assert success is True

    # Verify POST was called with correct parameters
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

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_response

    success = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8080/api/indexer/page",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert success is False


@pytest.mark.asyncio
async def test_submit_page_network_error():
    """Test network error during submission"""
    mock_session = MagicMock()
    mock_session.post.side_effect = Exception("Connection refused")

    success = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8080/api/indexer/page",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert success is False


@pytest.mark.asyncio
async def test_submit_page_timeout():
    """Test timeout during submission"""
    import asyncio

    mock_session = MagicMock()
    mock_session.post.side_effect = asyncio.TimeoutError()

    success = await submit_page_to_indexer(
        mock_session,
        "http://indexer:8080/api/indexer/page",
        "test-api-key",
        "http://example.com/test",
        "Test",
        "Content",
    )

    assert success is False


@pytest.mark.asyncio
async def test_submit_page_authentication():
    """Test API key is correctly included"""
    mock_response = AsyncMock()
    mock_response.status = 200

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_response

    api_key = "super-secret-key-12345"
    await submit_page_to_indexer(
        mock_session,
        "http://indexer:8080/api/indexer/page",
        api_key,
        "http://example.com",
        "Title",
        "Content",
    )

    # Verify API key in headers
    call_kwargs = mock_session.post.call_args[1]
    assert call_kwargs["headers"]["X-API-Key"] == api_key
