"""Tests for hybrid/semantic search mode dispatch and fallback."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest


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

        monkeypatch.setattr(search_service, "_run_opensearch_query", raise_error)

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

        monkeypatch.setattr(search_service, "_pgvector_search", raise_error)

        result = search_service.search("test", mode="semantic")
        assert isinstance(result, dict)
        assert "hits" in result

    def test_hybrid_search_strips_operators_before_embedding(self, monkeypatch):
        import shared.opensearch.search as opensearch_search
        from frontend.services.search import search_service

        embed = MagicMock(return_value=np.zeros(1536, dtype=np.float32))
        captured = {}

        def fake_search_hybrid(
            client,
            query_tokens,
            embedding,
            limit,
            offset,
            site_filter=None,
            exact_phrases=(),
            exclude_terms=(),
            exclude_phrases=(),
        ):
            captured["query_tokens"] = query_tokens
            captured["site_filter"] = site_filter
            captured["exact_phrases"] = exact_phrases
            captured["exclude_terms"] = exclude_terms
            captured["exclude_phrases"] = exclude_phrases
            return {"total": 0, "hits": []}

        monkeypatch.setattr(search_service, "_embed_query", embed)
        monkeypatch.setattr(search_service, "_os_client", MagicMock())
        monkeypatch.setattr(opensearch_search, "search_hybrid", fake_search_hybrid)

        result = search_service._run_opensearch_query(
            'site:github.com Python "open source" -java',
            10,
            1,
            with_embedding=True,
        )

        embed.assert_called_once_with("Python open source")
        assert captured["query_tokens"] == "python"
        assert captured["site_filter"] == "github.com"
        assert captured["exact_phrases"] == ("open source",)
        assert captured["exclude_terms"] == ("java",)
        assert captured["exclude_phrases"] == ()
        assert result.total == 0

    def test_vector_search_strips_operators_before_embedding(self, monkeypatch):
        import shared.embedding as shared_embedding
        import shared.postgres.search as postgres_search
        from frontend.services.search import search_service

        embed = MagicMock(return_value=np.zeros(1536, dtype=np.float32))
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cursor

        monkeypatch.setattr(search_service, "_embed_query", embed)
        monkeypatch.setattr(shared_embedding, "to_pgvector", lambda _: "[0.0,0.0,0.0]")
        monkeypatch.setattr(postgres_search, "get_connection", lambda *_: conn)

        result = search_service._pgvector_search(
            'site:github.com Python "open source" -java -"machine learning"',
            10,
            1,
        )

        embed.assert_called_once_with("Python open source")
        sql, params = cursor.execute.call_args.args
        assert "d.url ILIKE %s" in sql
        assert "%github.com%" in params
        assert "%open source%" in params
        assert "%java%" in params
        assert "%machine learning%" in params
        assert result.total == 0

    def test_vector_search_returns_empty_for_negative_only_query(self, monkeypatch):
        from frontend.services.search import search_service

        embed = MagicMock(return_value=np.zeros(1536, dtype=np.float32))
        monkeypatch.setattr(search_service, "_embed_query", embed)

        result = search_service._pgvector_search("site:github.com -java", 10, 1)

        embed.assert_not_called()
        assert result.total == 0
        assert result.hits == []


class TestAPISearchMode:
    def test_api_accepts_mode_parameter(self, client):
        resp = client.get("/api/v1/search", params={"q": "test", "mode": "bm25"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "bm25"

    def test_api_invalid_mode_defaults_to_auto(self, client):
        resp = client.get("/api/v1/search", params={"q": "test", "mode": "invalid"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "auto"

    def test_api_no_mode_defaults_to_auto(self, client):
        resp = client.get("/api/v1/search", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "auto"


class TestResultFormatting:
    def test_format_result_uses_positive_query_and_preserves_optional_fields(
        self, monkeypatch
    ):
        import frontend.services.search_response as search_response
        from frontend.services.search import search_service
        from shared.search_kernel.searcher import SearchHit, SearchResult

        captured = {}

        def fake_generate_snippet(content, search_terms):
            captured["content"] = content
            captured["search_terms"] = search_terms
            return SimpleNamespace(
                text="<mark>Python</mark> snippet", plain_text="Python snippet"
            )

        monkeypatch.setattr(search_response, "generate_snippet", fake_generate_snippet)

        result = SearchResult(
            query='site:github.com Python "open source" -java',
            total=1,
            hits=[
                SearchHit(
                    url="https://example.com",
                    title="Example",
                    content="Python open source content",
                    score=1.5,
                    indexed_at="2026-03-01T00:00:00+00:00",
                    published_at="2026-02-28T00:00:00+00:00",
                    temporal_anchor=0.9,
                    authorship_clarity=0.8,
                    factual_density=0.7,
                    origin_score=0.6,
                    origin_type="spring",
                    author="Alice",
                    organization="Example Org",
                    cluster_id=3,
                    sources_agreeing=5,
                )
            ],
            page=1,
            per_page=10,
            last_page=1,
            confidence="high",
            perspective_count=2,
            query_intent="overview",
        )

        payload = search_service._format_result(
            'site:github.com Python "open source" -java',
            result,
            include_content=True,
        )

        assert captured["content"] == "Python open source content"
        assert "github.com" not in captured["search_terms"]
        assert "java" not in captured["search_terms"]
        assert "python" in captured["search_terms"]
        assert payload["hits"][0]["content"] == "Python open source content"
        assert payload["hits"][0]["temporal_anchor"] == 0.9
        assert payload["hits"][0]["authorship_clarity"] == 0.8
        assert payload["hits"][0]["factual_density"] == 0.7
        assert payload["hits"][0]["origin_score"] == 0.6
        assert payload["hits"][0]["origin_type"] == "spring"
        assert payload["hits"][0]["author"] == "Alice"
        assert payload["hits"][0]["organization"] == "Example Org"
        assert payload["hits"][0]["cluster_id"] == 3
        assert payload["hits"][0]["sources_agreeing"] == 5
        assert payload["confidence"] == "high"
        assert payload["perspective_count"] == 2
        assert payload["query_intent"] == "overview"
