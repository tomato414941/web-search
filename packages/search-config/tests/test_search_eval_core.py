from web_search_search_config.canonical_sources import CanonicalEvalCase, EvalJudgment
from web_search_search_config.cli import validate_search_eval_config as module
from web_search_search_config.search_eval import canonical_search_eval_config
from web_search_search_config.evaluator import (
    classify_case,
    compute_case_metrics,
    hit_relevance,
)


def test_hit_relevance_prefers_explicit_judgments():
    case = CanonicalEvalCase(
        query="Example docs",
        query_type="reference",
        expected="docs.example.com",
        notes="Canonical docs should rank first",
        judgments=(
            EvalJudgment(
                relevance=2,
                domain="docs.example.com",
                path_prefix="/guide",
            ),
            EvalJudgment(
                relevance=3,
                url="https://docs.example.com/guide/getting-started",
            ),
        ),
    )
    hit = {
        "url": "https://docs.example.com/guide/getting-started",
        "title": "Getting Started",
        "snip": "",
        "snip_plain": "",
    }

    relevance = hit_relevance(
        case, hit, keyword_rules={}, known_domains=["docs.example.com"]
    )

    assert relevance == 3


def test_compute_case_metrics_uses_judgment_ideal_order():
    case = CanonicalEvalCase(
        query="Example docs",
        query_type="reference",
        expected="docs.example.com",
        notes="Canonical docs should rank first",
        judgments=(
            EvalJudgment(relevance=3, url="https://docs.example.com/"),
            EvalJudgment(relevance=2, domain="docs.example.com", path_prefix="/guide"),
        ),
    )
    payload = {
        "total": 2,
        "hits": [
            {
                "url": "https://docs.example.com/guide/getting-started",
                "title": "Guide",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://docs.example.com/",
                "title": "Home",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    metrics, relevances = compute_case_metrics(
        case,
        payload,
        keyword_rules={},
        known_domains=["docs.example.com"],
    )

    assert relevances == [2, 3]
    assert metrics["hit_at_1"] == 1.0
    assert metrics["hit_at_3"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["first_relevant_rank"] == 1
    assert round(float(metrics["ndcg_at_3"]), 3) == 0.834


def test_validate_query_cases_rejects_invalid_judgments():
    errors: list[str] = []

    module._validate_query_cases(
        [
            {
                "query": "Example docs",
                "query_type": "reference",
                "expected": "docs.example.com",
                "notes": "Example case",
                "judgments": [{"relevance": 4}],
            }
        ],
        {},
        errors,
    )

    assert "query_cases[1].judgments[1].relevance must be an integer in 1..3" in errors
    assert (
        "query_cases[1].judgments[1] must define url, domain, path_prefix, or title_terms"
        in errors
    )


def test_canonical_cases_derive_judgments_from_source_manifest():
    config = canonical_search_eval_config()
    react_case = next(case for case in config.query_cases if case.query == "React docs")
    python_news_case = next(
        case for case in config.query_cases if case.query == "Python 3.13 release"
    )

    assert any(
        judgment.domain == "react.dev" and judgment.path_prefix == "/reference"
        for judgment in react_case.judgments
    )
    assert any(
        judgment.domain == "docs.python.org"
        and judgment.path_prefix == "/3.13/whatsnew/3.13"
        for judgment in python_news_case.judgments
    )


def test_pattern_judgments_keep_ndcg_bounded():
    case = CanonicalEvalCase(
        query="Example docs",
        query_type="reference",
        expected="docs.example.com",
        notes="Canonical docs should rank first",
        judgments=(EvalJudgment(relevance=3, domain="docs.example.com"),),
    )
    payload = {
        "total": 3,
        "hits": [
            {"url": "https://docs.example.com/", "title": "Home"},
            {"url": "https://docs.example.com/guide", "title": "Guide"},
            {"url": "https://docs.example.com/reference", "title": "Reference"},
        ],
    }

    metrics, _ = compute_case_metrics(
        case,
        payload,
        keyword_rules={},
        known_domains=["docs.example.com"],
    )

    assert float(metrics["ndcg_at_3"]) == 1.0


def test_classify_case_supports_case_level_explicit_rules_without_keyword_map():
    case = CanonicalEvalCase(
        query="React docs",
        query_type="reference",
        expected="react.dev",
        notes="Official React docs should be in top 3",
        required_domains=("react.dev",),
        required_paths=("/reference", "/reference/"),
        pass_reason="top 3 include the main React docs entry points",
        fail_reason="top 3 do not include the main React docs entry points",
    )
    payload = {
        "total": 2,
        "hits": [
            {
                "url": "https://react.dev/reference",
                "title": "Reference",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://react.dev/learn",
                "title": "Learn",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    status, reason = classify_case(
        case,
        payload,
        keyword_rules={},
        known_domains=["react.dev"],
    )

    assert status == "pass"
    assert reason == "top 3 include the main React docs entry points"
