import numpy as np
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from frontend.services.search_opensearch import build_query_embedding
from frontend.services.search_query import build_opensearch_plan, prepare_search_query
from frontend.services.search_response import serialize_hit
from shared.search_kernel.searcher import SearchHit


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


def test_build_query_embedding_returns_list():
    search_query = prepare_search_query('site:github.com Python "open source" -java')
    embed_query = MagicMock(return_value=np.array([0.1, 0.2, 0.3], dtype=np.float32))

    embedding = build_query_embedding(
        search_query,
        embed_query,
        with_embedding=True,
    )

    embed_query.assert_called_once_with("Python open source")
    assert embedding == pytest.approx([0.1, 0.2, 0.3])


def test_serialize_hit_preserves_optional_fields(monkeypatch):
    import frontend.services.search_response as search_response

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
        temporal_anchor=0.9,
        authorship_clarity=0.8,
        factual_density=0.7,
        origin_score=0.6,
        origin_type="spring",
        author="Alice",
        organization="Example Org",
    )

    payload = serialize_hit(hit, ["python"], include_content=True)

    assert payload["snip"] == "<mark>python</mark>"
    assert payload["snip_plain"] == "Python content"
    assert payload["content"] == "Python content"
    assert payload["origin_type"] == "spring"
