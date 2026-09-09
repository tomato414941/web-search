from types import SimpleNamespace

from web_search_frontend.services.search import SearchService
from web_search_kernel.searcher import SearchHit, SearchResult


def test_search_service_returns_empty_result_when_opensearch_fails():
    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    service = SearchService(engine=SimpleNamespace(search=fail))

    result = service.search("test", 5, 1)

    assert result["query"] == "test"
    assert result["total"] == 0
    assert result["hits"] == []
    assert result["degraded"] is True
    assert result["error_type"] == "retrieval_failed"


def test_search_service_formats_bm25_result():
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

    service = SearchService(
        engine=SimpleNamespace(search=lambda *args, **kwargs: expected)
    )

    result = service.search("test", 10, 1)

    assert result["query"] == "test"
    assert result["total"] == 1
    assert result["mode"] == "bm25"
    assert "fallback" not in result
