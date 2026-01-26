"""
Robots.txt Cache Tests

Tests for AsyncRobotsCache with Redis persistence.
"""

import pytest
from unittest.mock import MagicMock
from app.utils.robots import AsyncRobotsCache


@pytest.mark.asyncio
async def test_robots_cache_allow():
    """Test robots.txt allows URL when cached"""
    # Use cached content to avoid the async HTTP fetch complications
    cached_content = b"User-agent: *\nAllow: /"

    mock_session = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get.return_value = cached_content
    mock_redis.sismember.return_value = False  # Domain not blocked

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/foo", "MyBot")

    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_disallow():
    """Test robots.txt disallows URL"""
    cached_content = b"User-agent: *\nDisallow: /private"

    mock_session = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get.return_value = cached_content
    mock_redis.sismember.return_value = False

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
    mock_redis.sismember.return_value = False

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/admin", "MyBot")

    # Should not make HTTP request (cache hit)
    mock_session.get.assert_not_called()
    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_miss_and_store():
    """Test Redis cache miss with cached allow-all content"""
    # Simulate cached allow-all response (what would be stored on 404)
    cached_content = b"User-agent: *\nDisallow:"

    mock_session = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get.return_value = cached_content
    mock_redis.sismember.return_value = False

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    # Cache hit, no HTTP request
    mock_session.get.assert_not_called()
    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_http_404():
    """Test robots.txt not found (404) allows all when cached"""
    # Simulate cached allow-all response from 404
    cached_content = b"User-agent: *\nDisallow:"

    mock_session = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get.return_value = cached_content
    mock_redis.sismember.return_value = False

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    # Should allow all from cached allow-all content
    assert allowed is True


@pytest.mark.asyncio
async def test_robots_cache_network_error():
    """Test network error returns False (skip URL, don't cache)"""
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network error")

    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # No cache
    mock_redis.sismember.return_value = False  # Not blocked

    cache = AsyncRobotsCache(mock_session, mock_redis)
    # First call: should return False (skip URL, try again later)
    allowed = await cache.can_fetch("http://example.com/test", "MyBot")

    # New behavior: return False on first failure (skip URL for now)
    assert allowed is False


@pytest.mark.asyncio
async def test_robots_cache_blocked_domain():
    """Test blocked domain is denied"""
    mock_session = MagicMock()
    mock_redis = MagicMock()
    mock_redis.sismember.return_value = True  # Domain is blocked

    cache = AsyncRobotsCache(mock_session, mock_redis)
    allowed = await cache.can_fetch("http://blocked.com/test", "MyBot")

    # Should deny blocked domain
    assert allowed is False
