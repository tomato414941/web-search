"""Test fixtures for shared package tests."""

import os

# Set ENVIRONMENT before importing any modules that use infrastructure_config
os.environ.setdefault("ENVIRONMENT", "test")

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables for testing."""
    # Remove all custom env vars to test defaults
    env_vars = [
        "CRAWLER_SERVICE_URL",
        "WEB_SERVER_URL",
        "REDIS_URL",
        "DB_PATH",
        "SECRET_KEY",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "INDEXER_API_KEY",
        "OPENAI_API_KEY",
        "CRAWL_CONCURRENCY",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def test_db_path(tmp_path):
    """Provide a temporary database path."""
    db_file = tmp_path / "test.db"
    return str(db_file)
