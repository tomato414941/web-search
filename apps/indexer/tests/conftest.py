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
    "url_referring_hosts",
    "link_outbox",
    "link_archive_batches",
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
        cur.execute("UPDATE link_archive_state SET pending_bytes = 0 WHERE singleton")
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


@pytest.fixture
def test_client(monkeypatch):
    from unittest.mock import MagicMock
    from web_search_indexer.services import indexer

    monkeypatch.setattr(indexer, "_get_opensearch_client", lambda: MagicMock())
    """Create FastAPI TestClient for the Indexer app."""
    from fastapi.testclient import TestClient
    from web_search_indexer.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def fake_embedding_service(monkeypatch):
    from types import SimpleNamespace
    from web_search_indexer.services import opensearch_document
    from web_search_opensearch.embeddings import DIMENSIONS

    monkeypatch.setattr(
        opensearch_document,
        "get_embeddings",
        lambda: SimpleNamespace(query=lambda text: [1.0] + [0.0] * (DIMENSIONS - 1)),
    )
