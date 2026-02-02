"""
Robots.txt Cache Tests

Tests for AsyncRobotsCache with in-memory LRU caching.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from app.utils.robots import AsyncRobotsCache


@pytest.mark.asyncio
async def test_robots_cache_allow():
    """Test robots.txt allows URL"""
    mock_session = MagicMock()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="User-agent: *\nAllow: /")
    mock_session.get.return_value.__aenter__.return_value = mock_response

    cache = AsyncRobotsCache(mock_session)
    allowed = await cache.can_fetch("http://example.com/foo", "MyBot")

    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_disallow():
    """Test robots.txt disallows URL"""
    mock_session = MagicMock()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="User-agent: *\nDisallow: /private")
    mock_session.get.return_value.__aenter__.return_value = mock_response

    cache = AsyncRobotsCache(mock_session)
    allowed = await cache.can_fetch("http://example.com/private/doc", "MyBot")

    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_hit():
    """Test in-memory cache hit (no second HTTP request)"""
    mock_session = MagicMock()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="User-agent: *\nDisallow: /admin")
    mock_session.get.return_value.__aenter__.return_value = mock_response

    cache = AsyncRobotsCache(mock_session)

    # First call - should make HTTP request
    await cache.can_fetch("http://example.com/admin", "MyBot")
    assert mock_session.get.call_count == 1

    # Second call - should use cache
    allowed = await cache.can_fetch("http://example.com/admin/test", "MyBot")
    assert mock_session.get.call_count == 1  # No additional request
    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_miss_and_store():
    """Test cache miss triggers HTTP request and stores result"""
    mock_session = MagicMock()

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="User-agent: *\nAllow: /")
    mock_session.get.return_value.__aenter__.return_value = mock_response

    cache = AsyncRobotsCache(mock_session)

    # First call
    allowed1 = await cache.can_fetch("http://example.com/test", "MyBot")
    assert allowed1 is True
    assert mock_session.get.call_count == 1

    # Second call - same domain, should use cache
    allowed2 = await cache.can_fetch("http://example.com/other", "MyBot")
    assert allowed2 is True
    assert mock_session.get.call_count == 1  # No additional request


@pytest.mark.asyncio
async def test_robots_cache_http_404():
    """Test robots.txt not found (404) allows all"""
    mock_session = MagicMock()

    # Mock 404 response
    mock_response = AsyncMock()
    mock_response.status = 404
    mock_session.get.return_value.__aenter__.return_value = mock_response

    cache = AsyncRobotsCache(mock_session)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    # Should allow all when robots.txt is not found
    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_network_error():
    """Test network error returns False (skip URL, don't cache)"""
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network error")

    cache = AsyncRobotsCache(mock_session)

    # First call: should return False (skip URL, try again later)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_blocked_domain():
    """Test blocked domain (after repeated failures) is denied"""
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network error")

    cache = AsyncRobotsCache(mock_session)

    # Simulate 3 failures to trigger blocking
    for _ in range(3):
        await cache.can_fetch("http://blocked.com/test", "MyBot")

    # Domain should now be blocked
    allowed = await cache.can_fetch("http://blocked.com/another", "MyBot")

    assert allowed is False
