import gc
import time
import os
import pytest
import fakeredis
from unittest.mock import patch
from shared.db.search import ensure_db
from shared.search import SearchEngine, BM25Config

# Patch DB_PATH to use a test database
TEST_DB_PATH = "test_search.db"
# Should match the path resolved by core.settings.
# But we patch the attribute on the instance.


@pytest.fixture(autouse=True)
def setup_test_env():
    # 1. Setup Test DB with retry logic
    if os.path.exists(TEST_DB_PATH):
        # Force garbage collection to close file handles
        gc.collect()

        # Retry removing the file
        for attempt in range(3):
            try:
                os.remove(TEST_DB_PATH)
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.2 * (attempt + 1))  # Increasing wait
                    gc.collect()

    ensure_db(TEST_DB_PATH)

    # Patch settings.DB_PATH
    with patch("frontend.core.config.settings.DB_PATH", TEST_DB_PATH):
        # Also patch the instantiated search_service's db_path because it was initialized at import time
        from frontend.services.search import search_service
        from frontend.services.embedding import embedding_service

        original_search_path = search_service.db_path
        search_service.db_path = TEST_DB_PATH

        # Reinitialize the internal SearchEngine with the test DB path
        search_service._engine = SearchEngine(
            db_path=TEST_DB_PATH,
            bm25_config=BM25Config(
                k1=1.2,
                b=0.75,
                title_boost=3.0,
                pagerank_weight=0.5,
            ),
            embed_query_func=search_service._embed_query,
            deserialize_func=embedding_service.deserialize,
        )

        yield

        search_service.db_path = original_search_path

    # Cleanup with retry
    if os.path.exists(TEST_DB_PATH):
        gc.collect()
        for attempt in range(3):
            try:
                os.remove(TEST_DB_PATH)
                break
            except (PermissionError, OSError):
                if attempt < 2:
                    time.sleep(0.1)


@pytest.fixture(autouse=True)
def mock_redis_server():
    r = fakeredis.FakeRedis(decode_responses=True)
    # Patch redis.Redis.from_url so any call to it returns our fake client
    with patch("redis.Redis.from_url", return_value=r):
        yield r


@pytest.fixture
def test_db_path(tmp_path):
    """Provide a temporary database path for tests."""
    db_path = tmp_path / "test.db"
    yield str(db_path)
    # Cleanup handled by tmp_path fixture
