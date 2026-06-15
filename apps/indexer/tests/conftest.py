"""Pytest configuration for Indexer service tests."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("INDEXER_API_KEY", "test-api-key")

from web_search_core.testing import ensure_test_pg
from web_search_postgres.migrate import migrate
from web_search_postgres.search import get_connection
import pytest

ensure_test_pg()

_TABLES = [
    "search_result_clicks",
    "search_result_impressions",
    "search_requests",
    "page_ranks",
    "documents",
    "domain_ranks",
    "links",
    "urls",
    "crawl_logs",
]


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    migrate()


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    conn = get_connection()
    try:
        conn.rollback()
        cur = conn.cursor()
        for table in _TABLES:
            try:
                cur.execute(f"TRUNCATE {table} CASCADE")
                conn.commit()
            except Exception:
                conn.rollback()
        cur.close()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


@pytest.fixture
def test_client():
    """Create FastAPI TestClient for the Indexer app."""
    from fastapi.testclient import TestClient
    from web_search_indexer.main import app

    return TestClient(app)
