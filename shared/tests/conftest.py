import os

os.environ.setdefault("ENVIRONMENT", "test")

from shared.testing import ensure_test_pg

ensure_test_pg()

import pytest  # noqa: E402
from shared.postgres.search import ensure_db, get_connection  # noqa: E402
from shared.postgres.migrate import _ensure_version_table  # noqa: E402

# Tables to truncate between tests (order matters for FK deps)
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
]


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    ensure_db()
    # Ensure schema_version table exists (normally created by migrate runner)
    conn = get_connection()
    try:
        _ensure_version_table(conn)
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    conn = get_connection()
    try:
        conn.rollback()
        cur = conn.cursor()
        # Build a single TRUNCATE statement for all tables
        cur.execute(f"TRUNCATE {', '.join(_TABLES)} CASCADE")
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
