import os
import time
import pytest
import numpy as np
from unittest.mock import patch
from shared.db.sqlite import open_db, upsert_page
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
        # 1. Initialize Service with SHORT TTL
        svc = SearchService(db_path=db_path)
        svc.CACHE_TTL = 2.0  # 2 seconds for test

        # 2. Add Item A
        con = open_db(db_path)
        url_a = "http://a.com"
        content_a = "Apple"
        upsert_page(con, url_a, "TitleA", content_a)
        vec_a = embedding_service.embed(content_a)
        con.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)", (url_a, vec_a)
        )
        con.commit()
        con.close()

        # 3. Initial Search (loads cache)
        res = svc.search("Fruit", mode="semantic")
        assert len(res["hits"]) == 1, "Should find A"

        # 4. Add Item B (Banana) *after* cache loaded
        con = open_db(db_path)
        url_b = "http://b.com"
        content_b = "Banana"
        upsert_page(con, url_b, "TitleB", content_b)
        vec_b = embedding_service.embed(content_b)
        con.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)", (url_b, vec_b)
        )
        con.commit()
        con.close()

        # 5. Fast Search (Should hit cached stale data)
        res = svc.search("Fruit", mode="semantic")
        assert len(res["hits"]) == 1, "Should still see only A (cached)"

        # 6. Wait for TTL
        time.sleep(2.1)

        # 7. Search Again (Should trigger refresh)
        res = svc.search("Fruit", mode="semantic")
        assert len(res["hits"]) == 2, "Should find A and B (refreshed)"
