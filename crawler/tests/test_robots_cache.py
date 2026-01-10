"""
Robots.txt Cache Tests

Tests for AsyncRobotsCache with Redis persistence.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from app.utils.robots import AsyncRobotsCache


@pytest.mark.asyncio
async def test_robots_cache_allow():
    """Test robots.txt allows URL"""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = "User-agent: *\nAllow: /"

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_response

    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # Cache miss

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/foo", "MyBot")

    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_disallow():
    """Test robots.txt disallows URL"""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = "User-agent: *\nDisallow: /private"

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_response

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/private/doc", "MyBot")

    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_hit():
    """Test Redis cache hit (no HTTP request)"""
    cached_content = b"User-agent: *\nDisallow: /admin"

    mock_session = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get.return_value = cached_content

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/admin", "MyBot")

    # Should not make HTTP request (cache hit)
    mock_session.get.assert_not_called()
    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_miss_and_store():
    """Test Redis cache miss triggers HTTP fetch and storage"""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = "User-agent: *\nAllow: /"

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_response

    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # Cache miss

    cache = AsyncRobotsCache(mock_session, mock_redis)
    await cache.can_fetch("http://example.com/test", "MyBot")

    # Should make HTTP request
    mock_session.get.assert_called_once()

    # Should store in Redis with TTL (24 hours = 86400 seconds)
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args[0]
    assert "robots:example.com" in call_args[0]  # Redis key
    assert call_args[1] == 86400  # TTL


@pytest.mark.asyncio
async def test_robots_cache_http_404():
    """Test robots.txt not found (404) allows all"""
    mock_response = AsyncMock()
    mock_response.status = 404

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_response

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    # Should allow all if robots.txt not found
    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_network_error():
    """Test network error allows all (fail open)"""
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network error")

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    # Should allow all on error (fail open)
    assert allowed is True
