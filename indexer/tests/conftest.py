"""Pytest configuration for Indexer service tests."""

import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("INDEXER_API_KEY", "test-api-key")

# Add indexer/src and shared/src to path for imports
indexer_root = Path(__file__).parent.parent
sys.path.insert(0, str(indexer_root / "src"))
sys.path.insert(0, str(indexer_root.parent / "shared" / "src"))

from shared.testing import ensure_test_pg  # noqa: E402

ensure_test_pg()

import pytest  # noqa: E402
from shared.postgres.search import get_connection  # noqa: E402
from shared.postgres.migrate import migrate  # noqa: E402

_TABLES = [
    "index_jobs",
    "search_events",
    "search_logs",
    "page_embeddings",
    "page_ranks",
    "documents",
    "domain_ranks",
    "links",
    "api_keys",
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
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)
