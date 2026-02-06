"""
Test configuration and fixtures for Crawler tests
"""

import os

# Set ENVIRONMENT before importing any modules that use infrastructure_config
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("INDEXER_API_KEY", "test-api-key")
os.environ.setdefault("INDEXER_API_URL", "http://test:8000/api/indexer/page")

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set required environment variables for tests"""
    os.environ["ENVIRONMENT"] = "test"
    os.environ["INDEXER_API_URL"] = "http://test:8000/api/indexer/page"
    os.environ["INDEXER_API_KEY"] = "test-api-key"
    os.environ["CRAWLER_HISTORY_DB"] = "/tmp/test_crawler_history.db"


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path for testing"""
    return str(tmp_path / "test_crawler.db")


@pytest.fixture
def test_url_store(temp_db_path):
    """Create a test UrlStore instance"""
    from app.db import UrlStore

    return UrlStore(temp_db_path, recrawl_after_days=30)


@pytest.fixture
def test_client(temp_db_path):
    """FastAPI test client with temporary database"""
    # Set the database path before importing app
    os.environ["CRAWLER_DB_PATH"] = temp_db_path

    from app.main import app

    return TestClient(app)


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
