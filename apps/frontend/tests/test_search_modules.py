from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from web_search_frontend.services.search import SearchService
from web_search_frontend.services.search_opensearch import (
    execute_opensearch_search,
    run_opensearch_query,
)
from web_search_frontend.services.search_query import prepare_search_query
from web_search_kernel.searcher import SearchHit, SearchResult


def test_execute_opensearch_search_uses_bm25_without_embedding(monkeypatch):
    import web_search_opensearch.search as opensearch_search

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
    )

    assert result == {"total": 0, "hits": []}
    assert captured["query_tokens"] == "python"
    assert captured["site_filter"] == "github.com"
    assert captured["exact_phrases"] == ("open source",)
    assert captured["exclude_terms"] == ("java",)
    assert captured["exclude_phrases"] == ("machine learning",)
    assert captured["limit"] == 10
    assert captured["offset"] == 20
    assert captured["retrieval_boosts"] is None


def test_run_opensearch_query_uses_plain_result_for_site_filter(monkeypatch):
    import web_search_frontend.services.search_opensearch as search_opensearch

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
        client,
        search_query,
        plan,
        required_domains=(),
        retrieval_boosts=None,
    ):
        captured["client"] = client
        captured["plan"] = plan
        captured["search_query"] = search_query
        captured["required_domains"] = required_domains
        captured["retrieval_boosts"] = retrieval_boosts
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
    assert captured["required_domains"] == ()
    assert captured["retrieval_boosts"] is None


def test_run_opensearch_query_fetches_extra_candidates_for_navigational_query(
    monkeypatch,
):
    import web_search_frontend.services.search_opensearch as search_opensearch

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
        client,
        search_query,
        plan,
        required_domains=(),
        retrieval_boosts=None,
    ):
        captured["plan"] = plan
        captured["client"] = client
        captured["required_domains"] = required_domains
        captured["retrieval_boosts"] = retrieval_boosts
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
    assert captured["retrieval_boosts"].host_path.hosts == ("github.com",)
    assert captured["retrieval_boosts"].host_path.paths == ("/",)
    assert captured["required_domains"] == ()
    assert captured["retrieval_boosts"].subject_phrase is None
    assert [hit.url for hit in result.hits] == [
        "https://github.com/",
        "https://github.com/org/repo",
    ]


def test_run_opensearch_query_rewrites_tokens_for_source_specific_docs(monkeypatch):
    import web_search_frontend.services.search_opensearch as search_opensearch

    captured = {}

    def fake_execute(
        client,
        search_query,
        plan,
        required_domains=(),
        retrieval_boosts=None,
    ):
        captured["tokens"] = search_query.tokens
        captured["positive_query"] = search_query.positive_query
        captured["required_domains"] = required_domains
        captured["retrieval_boosts"] = retrieval_boosts
        return {"total": 0, "hits": []}

    monkeypatch.setattr(search_opensearch, "execute_opensearch_search", fake_execute)

    run_opensearch_query(
        "React docs",
        3,
        1,
        client=MagicMock(),
        search_query=prepare_search_query("React docs"),
    )

    assert captured["tokens"] == "react reference overview"
    assert captured["positive_query"] == "react reference overview"
    assert captured["retrieval_boosts"].host_path.hosts == ("react.dev",)
    assert captured["required_domains"] == ("react.dev",)
    assert captured["retrieval_boosts"].subject_phrase is None


@pytest.mark.parametrize(
    ("query", "expected_tokens", "expected_domains"),
    (
        (
            "Docker compose file reference",
            "docker compose file reference",
            ("docs.docker.com",),
        ),
        (
            "Django model field reference",
            "django model field reference",
            ("docs.djangoproject.com",),
        ),
        ("pytest fixture", "pytest fixture", ("docs.pytest.org",)),
    ),
)
def test_run_opensearch_query_preserves_specific_reference_tokens(
    monkeypatch, query, expected_tokens, expected_domains
):
    import web_search_frontend.services.search_opensearch as search_opensearch

    captured = {}

    def fake_execute(
        client,
        search_query,
        plan,
        required_domains=(),
        retrieval_boosts=None,
    ):
        captured["tokens"] = search_query.tokens
        captured["positive_query"] = search_query.positive_query
        captured["required_domains"] = required_domains
        captured["retrieval_boosts"] = retrieval_boosts
        return {"total": 0, "hits": []}

    monkeypatch.setattr(search_opensearch, "execute_opensearch_search", fake_execute)

    run_opensearch_query(
        query,
        3,
        1,
        client=MagicMock(),
        search_query=prepare_search_query(query),
    )

    assert captured["tokens"] == expected_tokens
    assert captured["positive_query"] == query
    assert captured["retrieval_boosts"].host_path.hosts == expected_domains
    assert captured["required_domains"] == expected_domains
    assert captured["retrieval_boosts"].subject_phrase is None


def test_run_opensearch_query_passes_subject_phrase_boosts(monkeypatch):
    import web_search_frontend.services.search_opensearch as search_opensearch

    captured = {}

    def fake_execute(
        client,
        search_query,
        plan,
        required_domains=(),
        retrieval_boosts=None,
    ):
        captured["plan"] = plan
        captured["tokens"] = search_query.tokens
        captured["positive_query"] = search_query.positive_query
        captured["retrieval_boosts"] = retrieval_boosts
        captured["required_domains"] = required_domains
        return {"total": 0, "hits": []}

    monkeypatch.setattr(search_opensearch, "execute_opensearch_search", fake_execute)

    run_opensearch_query(
        "FastAPI vs Django",
        3,
        1,
        client=MagicMock(),
        search_query=prepare_search_query("FastAPI vs Django"),
    )

    assert captured["plan"].fetch_size == 100
    assert captured["tokens"] == "fastapi django"
    assert captured["positive_query"] == "fastapi django"
    assert captured["retrieval_boosts"].subject_phrase.subjects == ("fastapi", "django")
    assert captured["retrieval_boosts"].host_path is None
    assert captured["required_domains"] == ()


def test_search_service_returns_empty_result_when_opensearch_fails(monkeypatch):
    service = SearchService()

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_run_bm25_opensearch", fail)

    result = service.search("test", 5, 1)

    assert result["query"] == "test"
    assert result["total"] == 0
    assert result["hits"] == []
    assert result["degraded"] is True
    assert result["error_type"] == "retrieval_failed"


def test_search_service_formats_bm25_result(monkeypatch):
    service = SearchService()
    expected = SearchResult(
        query="test",
        total=1,
        hits=[
            SearchHit(
                url="https://example.com",
                title="Example",
                content="snippet body",
                score=1.0,
            )
        ],
        page=1,
        per_page=10,
        last_page=1,
    )

    monkeypatch.setattr(
        service, "_run_bm25_opensearch", lambda *args, **kwargs: expected
    )

    result = service.search("test", 10, 1)

    assert result["query"] == "test"
    assert result["total"] == 1
    assert result["mode"] == "bm25"
    assert "fallback" not in result
