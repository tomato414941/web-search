"""Tests for hybrid/semantic search mode dispatch and fallback."""

import numpy as np
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_embedding_funcs():
    """Provide mock embedding functions for hybrid search tests."""
    embed_fn = MagicMock(return_value=np.zeros(1536, dtype=np.float32))
    deserialize_fn = MagicMock(return_value=np.zeros(1536, dtype=np.float32))
    return embed_fn, deserialize_fn


class TestSearchModeDispatch:
    def test_bm25_mode_does_not_call_hybrid(self, monkeypatch):
        from frontend.services.search import search_service

        called = {"hybrid": False, "bm25": False}
        original_bm25 = search_service._bm25_search

        def track_bm25(*a, **kw):
            called["bm25"] = True
            return original_bm25(*a, **kw)

        def track_hybrid(*a, **kw):
            called["hybrid"] = True
            return {
                "query": "x",
                "total": 0,
                "hits": [],
                "page": 1,
                "per_page": 10,
                "last_page": 1,
            }

        monkeypatch.setattr(search_service, "_bm25_search", track_bm25)
        monkeypatch.setattr(search_service, "_hybrid_search", track_hybrid)

        search_service.search("test", mode="bm25")
        assert called["bm25"] is True
        assert called["hybrid"] is False

    def test_auto_mode_uses_bm25_when_no_embeddings(self):
        from frontend.services.search import search_service

        # conftest creates engine without embed_query_func
        assert search_service.hybrid_available is False
        result = search_service.search("test", mode="auto")
        assert result["total"] >= 0  # Just ensure it doesn't crash

    def test_hybrid_mode_falls_back_when_unavailable(self):
        from frontend.services.search import search_service

        assert search_service.hybrid_available is False
        result = search_service.search("test", mode="hybrid")
        assert result["total"] >= 0  # Falls back to BM25


class TestHybridFallbackOnError:
    def test_hybrid_search_catches_embedding_error(self, monkeypatch):
        from frontend.services.search import search_service

        # Temporarily make hybrid_available True
        monkeypatch.setattr(
            type(search_service), "hybrid_available", property(lambda self: True)
        )

        def raise_error(*a, **kw):
            raise RuntimeError("OpenAI API error")

        monkeypatch.setattr(search_service._engine, "hybrid_search", raise_error)

        result = search_service.search("test", mode="hybrid")
        assert isinstance(result, dict)
        assert "hits" in result

    def test_vector_search_catches_embedding_error(self, monkeypatch):
        from frontend.services.search import search_service

        monkeypatch.setattr(
            type(search_service), "hybrid_available", property(lambda self: True)
        )

        def raise_error(*a, **kw):
            raise RuntimeError("OpenAI API error")

        monkeypatch.setattr(search_service._engine, "vector_search", raise_error)

        result = search_service.search("test", mode="semantic")
        assert isinstance(result, dict)
        assert "hits" in result


class TestAPISearchMode:
    def test_api_accepts_mode_parameter(self):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/search", params={"q": "test", "mode": "bm25"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "bm25"

    def test_api_invalid_mode_defaults_to_auto(self):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/search", params={"q": "test", "mode": "invalid"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "auto"

    def test_api_no_mode_defaults_to_auto(self):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/search", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "auto"
