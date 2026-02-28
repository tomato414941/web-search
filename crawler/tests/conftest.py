"""
Test configuration and fixtures for Crawler tests
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("INDEXER_API_KEY", "test-api-key")
os.environ.setdefault("INDEXER_API_URL", "http://test:8000/api/indexer/page")

from shared.testing import ensure_test_pg

ensure_test_pg()

from shared.postgres.migrate import migrate  # noqa: E402

# Crawler tables to truncate
_CRAWLER_TABLES = ["urls", "crawl_logs"]


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    migrate()


@pytest.fixture(autouse=True)
def _clean_crawler_tables():
    yield
    from shared.db.search import get_connection

    conn = get_connection()
    try:
        conn.rollback()
        cur = conn.cursor()
        # Truncate each table separately so missing tables don't block others
        for table in _CRAWLER_TABLES:
            try:
                cur.execute(f"TRUNCATE {table} CASCADE")
                conn.commit()
            except Exception:
                conn.rollback()
        cur.close()
    finally:
        conn.close()


@pytest.fixture
def temp_db_path():
    """Kept for backward compatibility. Returns None."""
    return None


@pytest.fixture
def test_url_store():
    from app.db import UrlStore

    store = UrlStore("/unused", recrawl_after_days=30)
    return store


@pytest.fixture
def test_client():
    from app.api.deps import verify_api_key
    from app.main import app

    app.dependency_overrides[verify_api_key] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(verify_api_key, None)


@pytest.fixture
def reset_worker_manager():
    from app.workers.manager import worker_manager

    if worker_manager.is_running:
        import asyncio

        asyncio.run(worker_manager.stop(graceful=False))

    yield

    if worker_manager.is_running:
        import asyncio

        asyncio.run(worker_manager.stop(graceful=False))
