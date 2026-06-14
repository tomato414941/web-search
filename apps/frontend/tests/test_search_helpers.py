from types import SimpleNamespace

from web_search_frontend.services.search_query import (
    build_opensearch_plan,
    prepare_search_query,
)
from web_search_frontend.services.search_response import serialize_hit
from web_search_kernel.searcher import SearchHit


def test_build_opensearch_plan_disables_diversity_without_site_filter():
    search_query = prepare_search_query("python")

    plan = build_opensearch_plan(
        search_query,
        10,
        3,
        overscan=4,
        candidate_limit=200,
    )

    assert plan.use_diversity is False
    assert plan.fetch_size == 10
    assert plan.fetch_offset == 20


def test_build_opensearch_plan_disables_overscan_for_site_filter():
    search_query = prepare_search_query("site:github.com python")

    plan = build_opensearch_plan(
        search_query,
        10,
        3,
        overscan=4,
        candidate_limit=200,
    )

    assert plan.use_diversity is False
    assert plan.fetch_size == 10
    assert plan.fetch_offset == 20


def test_prepare_search_query_strips_english_question_prefix():
    search_query = prepare_search_query("What is BM25")

    assert search_query.tokens == "bm25"
    assert search_query.positive_query == "BM25"


def test_serialize_hit_preserves_optional_fields(monkeypatch):
    import web_search_frontend.services.search_response as search_response

    monkeypatch.setattr(
        search_response,
        "generate_snippet",
        lambda content, search_terms: SimpleNamespace(
            text=f"<mark>{search_terms[0]}</mark>",
            plain_text=content,
        ),
    )

    hit = SearchHit(
        url="https://example.com",
        title="Example",
        content="Python content",
        score=1.0,
        indexed_at="2026-03-01T00:00:00+00:00",
        published_at="2026-02-28T00:00:00+00:00",
        page_rank=0.5,
        domain_rank=0.4,
    )

    payload = serialize_hit(hit, ["python"], include_content=True)

    assert payload["snip"] == "<mark>python</mark>"
    assert payload["snip_plain"] == "Python content"
    assert payload["score"] == 1.0
    assert "rank" not in payload
    assert payload["content"] == "Python content"
    assert payload["page_rank"] == 0.5
    assert payload["domain_rank"] == 0.4
    assert payload["published_at"] == "2026-02-28T00:00:00+00:00"
