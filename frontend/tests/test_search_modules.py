from types import SimpleNamespace
from unittest.mock import MagicMock

from frontend.services.search_opensearch import (
    execute_opensearch_search,
    run_opensearch_query,
)
from frontend.services.search_query import prepare_search_query
from shared.search_kernel.searcher import SearchHit, SearchResult


def test_execute_opensearch_search_uses_bm25_without_embedding(monkeypatch):
    import shared.opensearch.search as opensearch_search

    captured = {}

    def fake_search_bm25(**kwargs):
        captured.update(kwargs)
        return {"total": 0, "hits": []}

    monkeypatch.setattr(opensearch_search, "search_bm25", fake_search_bm25)

    result = execute_opensearch_search(
        client=MagicMock(),
        search_query=prepare_search_query(
            'site:github.com Python "open source" -java -"machine learning"'
        ),
        plan=SimpleNamespace(fetch_size=10, fetch_offset=20),
        canonical_domains=("github.com",),
        canonical_paths=("/docs",),
    )

    assert result == {"total": 0, "hits": []}
    assert captured["query_tokens"] == "python"
    assert captured["site_filter"] == "github.com"
    assert captured["exact_phrases"] == ("open source",)
    assert captured["exclude_terms"] == ("java",)
    assert captured["exclude_phrases"] == ("machine learning",)
    assert captured["limit"] == 10
    assert captured["offset"] == 20
    assert captured["canonical_domains"] == ("github.com",)
    assert captured["canonical_paths"] == ("/docs",)


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
    )

    def fake_execute(
        client, search_query, plan, canonical_domains=(), canonical_paths=()
    ):
        captured["client"] = client
        captured["plan"] = plan
        captured["search_query"] = search_query
        captured["canonical_domains"] = canonical_domains
        captured["canonical_paths"] = canonical_paths
        return {"total": 25, "hits": raw_hits}

    monkeypatch.setattr(search_opensearch, "execute_opensearch_search", fake_execute)
    monkeypatch.setattr(
        search_opensearch, "build_search_hits", lambda hits: search_hits
    )
    monkeypatch.setattr(
        search_opensearch,
        "build_plain_opensearch_result",
        lambda *args, **kwargs: expected_result,
    )

    result = run_opensearch_query(
        "site:github.com python",
        10,
        3,
        client=MagicMock(),
        search_query=prepare_search_query("site:github.com python"),
    )

    assert result is expected_result
    assert captured["search_query"].parsed.site_filter == "github.com"
    assert captured["plan"].fetch_size == 10
    assert captured["plan"].fetch_offset == 20
    assert captured["canonical_domains"] == ()
    assert captured["canonical_paths"] == ()


def test_run_opensearch_query_fetches_extra_candidates_for_navigational_query(
    monkeypatch,
):
    import frontend.services.search_opensearch as search_opensearch

    captured = {}
    raw_hits = [
        {
            "url": "https://github.com/org/repo",
            "title": "Repo",
            "content": "x",
            "score": 10.0,
        },
        {
            "url": "https://github.com/",
            "title": "GitHub",
            "content": "x",
            "score": 5.0,
        },
    ]

    def fake_execute(
        client, search_query, plan, canonical_domains=(), canonical_paths=()
    ):
        captured["plan"] = plan
        captured["client"] = client
        captured["canonical_domains"] = canonical_domains
        captured["canonical_paths"] = canonical_paths
        return {"total": 25, "hits": raw_hits}

    monkeypatch.setattr(search_opensearch, "execute_opensearch_search", fake_execute)

    result = run_opensearch_query(
        "GitHub",
        3,
        1,
        client=MagicMock(),
        search_query=prepare_search_query("GitHub"),
    )

    assert captured["plan"].fetch_size == 100
    assert captured["canonical_domains"] == ("github.com",)
    assert captured["canonical_paths"] == ("/",)
    assert [hit.url for hit in result.hits] == [
        "https://github.com/",
        "https://github.com/org/repo",
    ]
