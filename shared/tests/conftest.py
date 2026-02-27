import os

os.environ.setdefault("ENVIRONMENT", "test")

from shared.testing import ensure_test_pg

ensure_test_pg()

import pytest  # noqa: E402
from shared.postgres.search import get_connection  # noqa: E402
from shared.postgres.migrate import migrate  # noqa: E402

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
