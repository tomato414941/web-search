from types import SimpleNamespace
import pytest

from web_search_frontend.services.search import SearchService, SearchUnavailable
from web_search_kernel.searcher import SearchHit, SearchResult


@pytest.mark.parametrize("error", [RuntimeError, ValueError])
def test_search_service_reports_dependency_failure(error):
    def fail(*args, **kwargs):
        raise error("boom")

    service = SearchService(engine=SimpleNamespace(search=fail))

    with pytest.raises(SearchUnavailable):
        service.search("test", 5, 1)


def test_search_service_formats_hybrid_result():
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
    assert result["mode"] == "hybrid"
    assert "fallback" not in result
