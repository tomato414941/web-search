from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from frontend.services.search_opensearch import (
    apply_scope_match,
    execute_opensearch_search,
    run_opensearch_query,
)
from frontend.services.search_pgvector import (
    append_document_filters,
    run_pgvector_search,
)
from frontend.services.search_query import prepare_search_query
from shared.search_kernel.searcher import SearchHit, SearchResult


def test_execute_opensearch_search_uses_bm25_without_embedding(monkeypatch):
    import shared.opensearch.search as opensearch_search

    captured = {}

    def fake_search_bm25(**kwargs):
        captured.update(kwargs)
        return {"total": 0, "hits": []}

    hybrid_search = MagicMock()
    monkeypatch.setattr(opensearch_search, "search_bm25", fake_search_bm25)
    monkeypatch.setattr(opensearch_search, "search_hybrid", hybrid_search)

    result = execute_opensearch_search(
        client=MagicMock(),
        search_query=prepare_search_query(
            'site:github.com Python "open source" -java -"machine learning"'
        ),
        plan=SimpleNamespace(fetch_size=10, fetch_offset=20),
        embedding=None,
    )

    assert result == {"total": 0, "hits": []}
    hybrid_search.assert_not_called()
    assert captured["query_tokens"] == "python"
    assert captured["site_filter"] == "github.com"
    assert captured["exact_phrases"] == ("open source",)
    assert captured["exclude_terms"] == ("java",)
    assert captured["exclude_phrases"] == ("machine learning",)
    assert captured["limit"] == 10
    assert captured["offset"] == 20


def test_execute_opensearch_search_uses_hybrid_with_embedding(monkeypatch):
    import shared.opensearch.search as opensearch_search

    bm25_search = MagicMock()
    hybrid_search = MagicMock(return_value={"total": 3, "hits": []})
    monkeypatch.setattr(opensearch_search, "search_bm25", bm25_search)
    monkeypatch.setattr(opensearch_search, "search_hybrid", hybrid_search)
    embedding = [0.1, 0.2, 0.3]

    result = execute_opensearch_search(
        client=MagicMock(),
        search_query=prepare_search_query("python tutorial"),
        plan=SimpleNamespace(fetch_size=5, fetch_offset=0),
        embedding=embedding,
    )

    assert result == {"total": 3, "hits": []}
    bm25_search.assert_not_called()
    hybrid_search.assert_called_once()
    assert hybrid_search.call_args.kwargs["embedding"] == embedding


def test_apply_scope_match_reorders_hits_for_known_intent():
    hits = [
        SearchHit(
            url="https://example.com/news/python-3-13",
            title="News",
            content="news",
            score=1.0,
        ),
        SearchHit(
            url="https://docs.example.com/api/python",
            title="Reference",
            content="docs",
            score=0.9,
        ),
    ]

    query_intent = apply_scope_match(hits, query="what is python")

    assert query_intent == "overview"
    assert hits[0].url == "https://docs.example.com/api/python"
    assert hits[0].score == pytest.approx(0.9)
    assert hits[1].score == pytest.approx(0.88)


def test_run_opensearch_query_uses_plain_result_for_site_filter(monkeypatch):
    import frontend.services.search_opensearch as search_opensearch

    captured = {}
    raw_hits = [{"url": "https://github.com/org/repo", "title": "Repo", "content": "x"}]
    search_hits = [
        SearchHit(
            url="https://github.com/org/repo",
            title="Repo",
            content="x",
            score=1.5,
        )
    ]
    expected_result = SearchResult(
        query="site:github.com python",
        total=25,
        hits=search_hits,
        page=3,
        per_page=10,
        last_page=3,
        query_intent="reference",
    )

    def fake_execute(client, search_query, plan, embedding):
        captured["client"] = client
        captured["plan"] = plan
        captured["embedding"] = embedding
        captured["search_query"] = search_query
        return {"total": 25, "hits": raw_hits}

    monkeypatch.setattr(search_opensearch, "execute_opensearch_search", fake_execute)
    monkeypatch.setattr(
        search_opensearch, "build_search_hits", lambda hits: search_hits
    )
    monkeypatch.setattr(
        search_opensearch, "apply_scope_match", lambda hits, query: "reference"
    )
    monkeypatch.setattr(
        search_opensearch,
        "build_plain_opensearch_result",
        lambda *args, **kwargs: expected_result,
    )
    monkeypatch.setattr(
        search_opensearch,
        "build_diversified_result",
        lambda *args, **kwargs: pytest.fail("diversity path should not be used"),
    )

    result = run_opensearch_query(
        "site:github.com python",
        10,
        3,
        client=MagicMock(),
        search_query=prepare_search_query("site:github.com python"),
        embed_query=MagicMock(),
    )

    assert result is expected_result
    assert captured["search_query"].parsed.site_filter == "github.com"
    assert captured["plan"].use_diversity is False
    assert captured["plan"].fetch_size == 10
    assert captured["plan"].fetch_offset == 20
    assert captured["embedding"] is None


def test_append_document_filters_uses_negated_clause_when_requested():
    where_clauses: list[str] = []
    params: list[str] = []

    append_document_filters(where_clauses, params, ("python",), negated=True)

    assert where_clauses == [
        "NOT (COALESCE(d.title, '') ILIKE %s OR COALESCE(d.content, '') ILIKE %s)"
    ]
    assert params == ["%python%", "%python%"]


def test_run_pgvector_search_uses_prepared_filters_and_clamps_page(monkeypatch):
    import shared.embedding as shared_embedding
    import shared.postgres.search as postgres_search

    cursor = MagicMock()
    cursor.fetchall.return_value = [
        (
            "https://example.com/a",
            "A",
            "alpha",
            0.91,
            None,
            None,
        ),
        (
            "https://example.com/b",
            "B",
            "beta",
            0.82,
            None,
            None,
        ),
        (
            "https://example.com/c",
            "C",
            "gamma",
            0.73,
            None,
            None,
        ),
    ]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    embed_query = MagicMock(return_value=[0.1, 0.2, 0.3])

    monkeypatch.setattr(shared_embedding, "to_pgvector", lambda _: "[0.1,0.2,0.3]")
    monkeypatch.setattr(postgres_search, "get_connection", lambda: conn)

    result = run_pgvector_search(
        'site:github.com Python "open source" -java -"machine learning"',
        2,
        99,
        search_query=prepare_search_query(
            'site:github.com Python "open source" -java -"machine learning"'
        ),
        embed_query=embed_query,
    )

    embed_query.assert_called_once_with("Python open source")
    sql, params = cursor.execute.call_args.args
    assert "d.url ILIKE %s" in sql
    assert "%github.com%" in params
    assert "%open source%" in params
    assert "%java%" in params
    assert "%machine learning%" in params
    assert params[-3:] == ("[0.1,0.2,0.3]", 3, 18)
    assert result.total == 21
    assert result.last_page == 10
    assert [hit.url for hit in result.hits] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_run_pgvector_search_returns_empty_without_positive_terms():
    embed_query = MagicMock()

    result = run_pgvector_search(
        "site:github.com -java",
        10,
        1,
        search_query=prepare_search_query("site:github.com -java"),
        embed_query=embed_query,
    )

    embed_query.assert_not_called()
    assert result.total == 0
    assert result.hits == []
