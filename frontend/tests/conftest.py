import os

# Set ENVIRONMENT before importing any modules that use infrastructure_config
os.environ.setdefault("ENVIRONMENT", "test")

# Set test environment variables before importing any app modules
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "test_password")
os.environ.setdefault("ADMIN_SESSION_SECRET", "test-secret-key-for-testing")

import gc
import time
import pytest
from unittest.mock import patch
from shared.db.search import ensure_db
from shared.search import SearchEngine, BM25Config

# Patch DB_PATH to use a test database
TEST_DB_PATH = "test_search.db"


@pytest.fixture(autouse=True)
def setup_test_env():
    if os.path.exists(TEST_DB_PATH):
        gc.collect()
        for attempt in range(3):
            try:
                os.remove(TEST_DB_PATH)
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.2 * (attempt + 1))
                    gc.collect()

    ensure_db(TEST_DB_PATH)

    with patch("frontend.core.config.settings.DB_PATH", TEST_DB_PATH):
        from frontend.services.search import search_service

        original_search_path = search_service.db_path
        search_service.db_path = TEST_DB_PATH

        search_service._engine = SearchEngine(
            db_path=TEST_DB_PATH,
            bm25_config=BM25Config(
                k1=1.2,
                b=0.75,
                title_boost=3.0,
                pagerank_weight=0.5,
            ),
        )

        yield

        search_service.db_path = original_search_path

    if os.path.exists(TEST_DB_PATH):
        gc.collect()
        for attempt in range(3):
            try:
                os.remove(TEST_DB_PATH)
                break
            except (PermissionError, OSError):
                if attempt < 2:
                    time.sleep(0.1)


@pytest.fixture
def test_db_path(tmp_path):
    """Provide a temporary database path for tests."""
    db_path = tmp_path / "test.db"
    yield str(db_path)
    # Cleanup handled by tmp_path fixture
