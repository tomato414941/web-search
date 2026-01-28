from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from frontend.api.main import app

client = TestClient(app)


def test_health():
    # Test /healthz endpoint (liveness probe)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_search_page_loads_default():
    # Helper to check if default load (en) contains "Search"
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Check for English title logic (assuming fallback is EN)
    assert "Search" in response.text


def test_search_page_lang_en():
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Search" in response.text
    assert "検索" not in response.text


def test_search_page_lang_ja():
    response = client.get("/?lang=ja")
    assert response.status_code == 200
    # "検索" should be present in title or button
    assert "検索" in response.text


def test_search_api_empty_query():
    response = client.get("/api/v1/search")
    assert response.status_code == 200
    data = response.json()
    assert data["hits"] == []
    assert data["total"] == 0


def test_search_api_with_query():
    # Mock embedding service since hybrid search requires OpenAI API
    dummy_vec = np.zeros(1536, dtype=np.float32)
    with patch("frontend.services.search.embedding_service") as mock_embed:
        mock_embed.embed_query.return_value = dummy_vec
        mock_embed.deserialize.return_value = dummy_vec
        response = client.get("/api/v1/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "test"
