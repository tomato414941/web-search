from frontend.services.search_query import prepare_search_query
from frontend.services.search_ranking_policy import (
    candidate_window_size,
    classify_query_policy,
    rerank_hits,
)
from shared.search_kernel.searcher import SearchHit


def test_classify_query_policy_marks_google_as_navigational():
    policy = classify_query_policy("Google", prepare_search_query("Google"))

    assert policy.query_class == "navigational"
    assert policy.source is not None
    assert policy.source.key == "google"


def test_classify_query_policy_marks_postgresql_jsonb_as_reference():
    policy = classify_query_policy(
        "PostgreSQL jsonb",
        prepare_search_query("PostgreSQL jsonb"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "postgresql"


def test_classify_query_policy_skips_news_queries():
    policy = classify_query_policy(
        "OpenAI news",
        prepare_search_query("OpenAI news"),
    )

    assert policy.query_class == "other"
    assert policy.source is None


def test_candidate_window_size_expands_first_page_for_canonical_queries():
    policy = classify_query_policy("GitHub", prepare_search_query("GitHub"))

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 20


def test_rerank_hits_promotes_canonical_homepage():
    policy = classify_query_policy("Google", prepare_search_query("Google"))
    hits = [
        SearchHit(
            url="https://vr.google.com/intl/ja_jp/cardboard/",
            title="Cardboard",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://google.com/",
            title="Google",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://cardboard.google.com/",
            title="Cardboard",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://google.com/",
        "https://vr.google.com/intl/ja_jp/cardboard/",
        "https://cardboard.google.com/",
    ]
