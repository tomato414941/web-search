import os
import sqlite3
import pytest
import numpy as np
from unittest.mock import patch
from shared.db.search import open_db
from shared.search import SearchIndexer
from frontend.services.search import SearchService
from frontend.services.embedding import embedding_service

# Use a separate DB for this test to avoid conflicts
TEST_DB_PATH = "test_refresh.db"


@pytest.fixture
def clean_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    # Init DB
    open_db(TEST_DB_PATH).close()

    yield TEST_DB_PATH

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass  # Sometimes windows holds lock


def test_cache_refresh_ttl(clean_db):
    """Verify that SearchService refreshes its cache after TTL expires."""
    db_path = clean_db

    # Setup Mock for OpenAI
    # Dimensions: 1536
    dummy_vec = np.zeros(1536, dtype=np.float32).tolist()

    with patch.object(embedding_service, "_get_embedding", return_value=dummy_vec):
        # 1. Initialize Service
        svc = SearchService(db_path=db_path)
        indexer = SearchIndexer(db_path)

        # 2. Add Item A using new indexer
        url_a = "http://a.com"
        indexer.index_document(url_a, "TitleA", "Apple")
        indexer.update_global_stats()

        # Add embedding
        vec_a = embedding_service.embed("Apple")
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)", (url_a, vec_a)
        )
        con.commit()
        con.close()

        # 3. Initial Search (loads cache)
        res = svc.search("Fruit", mode="semantic")
        assert len(res["hits"]) == 1, "Should find A"

        # 4. Add Item B (Banana) *after* cache loaded
        url_b = "http://b.com"
        indexer.index_document(url_b, "TitleB", "Banana")
        indexer.update_global_stats()

        vec_b = embedding_service.embed("Banana")
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)", (url_b, vec_b)
        )
        con.commit()
        con.close()

        # 5. Fast Search (Should hit cached stale data)
        res = svc.search("Fruit", mode="semantic")
        assert len(res["hits"]) == 1, "Should still see only A (cached)"

        # 6. Clear vector cache to simulate TTL expiry
        svc._engine.clear_vector_cache()

        # 7. Search Again (Should see refreshed data)
        res = svc.search("Fruit", mode="semantic")
        assert len(res["hits"]) == 2, "Should find A and B (refreshed)"
