import os

# Set ENVIRONMENT before importing any modules that use infrastructure_config
os.environ.setdefault("ENVIRONMENT", "test")

# Set test environment variables before importing any app modules
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "test_password")
os.environ.setdefault("ADMIN_SESSION_SECRET", "test-secret-key-for-testing")

import sqlite3

import pytest
from unittest.mock import patch
from shared.db.search import ensure_db
from shared.search import SearchEngine, BM25Config


def _apply_sqlite_extras(db_path: str) -> None:
    """Apply columns/tables that are pg_only in migrations but needed for tests."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE search_logs ADD COLUMN api_key_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            name TEXT NOT NULL,
            rate_limit_daily INTEGER NOT NULL DEFAULT 1000,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_used_at TEXT
        )"""
    )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    test_db_path = str(tmp_path / "test_search.db")
    ensure_db(test_db_path)
    _apply_sqlite_extras(test_db_path)

    with patch("frontend.core.config.settings.DB_PATH", test_db_path):
        from frontend.services.search import search_service

        original_search_path = search_service.db_path
        original_engine = search_service._engine
        search_service.db_path = test_db_path

        search_service._engine = SearchEngine(
            db_path=test_db_path,
            bm25_config=BM25Config(
                k1=1.2,
                b=0.75,
                title_boost=3.0,
                pagerank_weight=0.5,
            ),
        )

        yield

        search_service.db_path = original_search_path
        search_service._engine = original_engine


@pytest.fixture
def test_db_path(tmp_path):
    """Provide a temporary database path for tests."""
    db_path = tmp_path / "test.db"
    yield str(db_path)
    # Cleanup handled by tmp_path fixture
