import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "test_password")
os.environ.setdefault("ADMIN_SESSION_SECRET", "test-secret-key-for-testing")

from shared.testing import ensure_test_pg

ensure_test_pg()

import pytest  # noqa: E402
from shared.postgres.search import ensure_db, get_connection  # noqa: E402
from shared.postgres.migrate import migrate, _ensure_version_table  # noqa: E402

# Tables to truncate between tests
_TABLES = [
    "index_jobs",
    "search_events",
    "search_logs",
    "inverted_index",
    "token_stats",
    "index_stats",
    "page_embeddings",
    "page_ranks",
    "documents",
    "domain_ranks",
    "links",
    "schema_version",
    "api_keys",
]


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    ensure_db()
    # Ensure schema_version exists and apply migrations (creates api_keys etc.)
    conn = get_connection()
    try:
        _ensure_version_table(conn)
    finally:
        conn.close()
    migrate()


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    conn = get_connection()
    try:
        conn.rollback()
        cur = conn.cursor()
        cur.execute(f"TRUNCATE {', '.join(_TABLES)} CASCADE")
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


@pytest.fixture
def test_db_path():
    """Provide database access (kept for backward compat, returns None)."""
    yield None
