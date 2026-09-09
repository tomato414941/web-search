from web_search_engine.query import build_opensearch_plan, prepare_search_query


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
