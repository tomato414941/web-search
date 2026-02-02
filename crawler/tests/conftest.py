"""
Test configuration and fixtures for Crawler tests
"""

import os

# Set ENVIRONMENT before importing any modules that use infrastructure_config
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set required environment variables for tests"""
    os.environ["ENVIRONMENT"] = "test"
    os.environ["INDEXER_API_URL"] = "http://test:8000/api/indexer/page"
    os.environ["INDEXER_API_KEY"] = "test-api-key"
    os.environ["REDIS_URL"] = "redis://test:6379"
    os.environ["CRAWLER_HISTORY_DB"] = "/tmp/test_crawler_history.db"


@pytest.fixture
def test_client():
    """FastAPI test client"""
    from app.main import app

    return TestClient(app)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = MagicMock()
    redis.ping.return_value = True
    redis.zcard.return_value = 0
    redis.scard.return_value = 0
    redis.zrange.return_value = []
    redis.zpopmax.return_value = []
    redis.zadd.return_value = 1
    redis.sadd.return_value = 1
    redis.get.return_value = None
    redis.setex.return_value = True
    return redis


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp ClientSession"""
    session = MagicMock()

    # Mock response
    response = AsyncMock()
    response.status = 200
    response.headers = {"Content-Type": "text/html"}
    response.text = AsyncMock(return_value="<html><body>Test</body></html>")

    # Setup context manager
    session.get.return_value.__aenter__.return_value = response
    session.post.return_value.__aenter__.return_value = response

    return session


@pytest.fixture
def reset_worker_manager():
    """Reset worker manager state between tests"""
    from app.workers.manager import worker_manager

    # Stop worker if running
    if worker_manager.is_running:
        import asyncio

        asyncio.run(worker_manager.stop(graceful=False))

    yield

    # Cleanup after test
    if worker_manager.is_running:
        import asyncio

        asyncio.run(worker_manager.stop(graceful=False))
