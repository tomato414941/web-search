import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "test_password")
os.environ.setdefault("ADMIN_SESSION_SECRET", "test-secret-key-for-testing")

from shared.testing import ensure_test_pg

ensure_test_pg()

import pytest  # noqa: E402
from shared.db.search import get_connection  # noqa: E402
from shared.postgres.migrate import migrate  # noqa: E402

# Tables to truncate between tests
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
def test_db_path():
    """Provide database access (kept for backward compat, returns None)."""
    yield None
