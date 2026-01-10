import pytest
import os
import numpy as np
from unittest.mock import patch
from frontend.core.db import open_db, upsert_page
from frontend.services.search import SearchService
from frontend.services.embedding import embedding_service
from frontend.indexer.analyzer import analyzer


@pytest.fixture
def temp_db_semantic(tmp_path):
    db_path = tmp_path / "test_semantic.db"
    str_path = str(db_path)
    con = open_db(str_path)
    con.close()
    yield str_path
    if os.path.exists(str_path):
        os.remove(str_path)


def test_vector_search_semantics(temp_db_semantic):
    """
    Verify Vector Search finds semantically related items.
    Mocks OpenAI API to return compatible vectors.
    """
    # 1. Setup Mock
    # Create two arbitrary vectors that are similar (e.g., [1, 0, ...] vs [0.9, 0.1, ...])
    # Dimensions: 1536 for text-embedding-3-small
    dim = 1536

    # Vector A for Content
    vec_a = np.zeros(dim, dtype=np.float32)
    vec_a[0] = 1.0

    # Vector B for Query (similar to A)
    vec_b = np.zeros(dim, dtype=np.float32)
    vec_b[0] = 0.9
    vec_b[1] = 0.1

    # Mock the _get_embedding method instead of the whole client to keep it simple,
    # or mock the client. The service uses self.client.embeddings.create.

    # Let's mock _get_embedding on the global instance
    with patch.object(embedding_service, "_get_embedding") as mock_embed:
        # Define side effect: return vec_a for content, vec_b for query
        def side_effect(text):
            if "Pasta" in text or "Carbonara" in text:
                return vec_a.tolist()
            return vec_b.tolist()  # Default to query vector

        mock_embed.side_effect = side_effect

        # 2. Setup Data
        con = open_db(temp_db_semantic)

        # Insert "Cooking Pasta"
        url = "http://example.com/pasta"
        title = "Cooking Pasta"
        content = "Carbonara is a delicious Italian dish."

        # Normal Upsert
        t_idx = analyzer.tokenize(title)
        c_idx = analyzer.tokenize(content)
        upsert_page(con, url, t_idx, c_idx, title, content)

        # Embedding Upsert
        text = f"{title}. {content}"
        vec = embedding_service.embed(text)
        con.execute("DELETE FROM page_embeddings WHERE url=?", (url,))
        con.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)", (url, vec)
        )

        con.commit()
        con.close()

        # 3. Search
        svc = SearchService(db_path=temp_db_semantic)

        # Query that returns vec_b (via mock default)
        q_proven = "Delicious Food"

        # semantic search
        res = svc.search(q_proven, mode="semantic", k=5)

        found = False
        for hit in res["hits"]:
            if hit["url"] == url:
                found = True
                # Score should be high (cosine sim of [1,0..] and [0.9,0.1..] is near 1)
                assert hit["rank"] > 0.8
                break

        assert found, f"Vector search failed to find {title} for query '{q_proven}'"
