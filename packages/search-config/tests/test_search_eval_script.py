import json
import sys

from web_search_search_config.canonical_sources import CanonicalEvalCase
from web_search_search_config.cli import evaluate_search as module


def test_extract_domain_prefers_longest_known_domain_match():
    domain = module._extract_domain(
        "docs.github.com",
        ["github.com", "docs.github.com"],
    )

    assert domain == "docs.github.com"


def test_reference_case_requires_expected_docs_subdomain():
    case = CanonicalEvalCase(
        query="GitHub docs",
        query_type="reference",
        expected="docs.github.com",
        notes="Official GitHub docs should be in top 3",
    )
    payload = {
        "total": 3,
        "hits": [
            {
                "url": "https://github.com/",
                "title": "GitHub",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://github.com/actions",
                "title": "GitHub Actions",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://github.com/features/copilot",
                "title": "GitHub Copilot",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={},
        known_domains=["docs.github.com", "github.com"],
    )

    assert status == "fail"
    assert reason == "canonical docs missing from top 3"


def test_navigational_case_passes_when_official_homepage_is_top3():
    case = CanonicalEvalCase(
        query="GitHub",
        query_type="navigational",
        expected="github.com",
        notes="Official homepage should be in top 3",
    )
    payload = {
        "total": 3,
        "hits": [
            {
                "url": "https://docs.github.com/",
                "title": "GitHub Docs",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://github.blog/",
                "title": "GitHub Blog",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://github.com/",
                "title": "GitHub",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={},
        known_domains=["github.com", "docs.github.com"],
    )

    assert status == "pass"
    assert reason == "official destination is in top 3"


def test_domain_rule_respects_excluded_domains():
    case = CanonicalEvalCase(
        query="OpenAI announcements",
        query_type="news/reference",
        expected="official OpenAI announcements",
        notes="Top 3 should include an official OpenAI announcements page",
    )
    payload = {
        "total": 3,
        "hits": [
            {
                "url": "https://community.openai.com/c/announcements/6",
                "title": "Announcements",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://community.openai.com/t/devday-2025-is-here/1361200",
                "title": "DevDay 2025",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://developers.openai.com/api/docs/changelog",
                "title": "Changelog",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={
            "openai announcements": {
                "required_domains": ["openai.com"],
                "minimum_domain_matches": 1,
                "required_path_terms": ["/announcements", "/index", "/news"],
                "excluded_domains": ["community.openai.com", "developers.openai.com"],
                "pass_reason": "top 3 include an official OpenAI announcements page",
                "fail_reason": "top 3 do not include an official OpenAI announcements page",
            }
        },
        known_domains=["developers.openai.com", "openai.com"],
    )

    assert status == "fail"
    assert reason == "top 3 do not include an official OpenAI announcements page"


def test_explicit_rule_failure_returns_fail():
    case = CanonicalEvalCase(
        query="OpenAI news",
        query_type="news/reference",
        expected="recent official OpenAI news or blog reporting",
        notes="Top 3 should include an official OpenAI news/blog result",
    )
    payload = {"total": 0, "hits": []}

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={
            "openai news": {
                "required_domains": ["openai.com"],
                "minimum_domain_matches": 1,
                "required_path_terms": ["/blog", "/news", "/index", "/announcements"],
                "excluded_domains": ["community.openai.com"],
                "pass_reason": "top 3 include an official OpenAI news or blog result",
                "fail_reason": "top 3 do not include an official OpenAI news or blog result",
            }
        },
        known_domains=["openai.com"],
    )

    assert status == "fail"
    assert reason == "0 hits"


def test_domain_rule_can_require_exact_paths_and_rank_window():
    case = CanonicalEvalCase(
        query="React docs",
        query_type="reference",
        expected="react.dev",
        notes="Official React docs should be in top 3",
    )
    payload = {
        "total": 3,
        "hits": [
            {
                "url": "https://react.dev/versions",
                "title": "React versions",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://react.dev/blog",
                "title": "React blog",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://react.dev/reference/react/useEffect",
                "title": "useEffect",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={
            "react docs": {
                "required_domains": ["react.dev"],
                "required_paths": [
                    "/",
                    "/learn",
                    "/learn/",
                    "/reference",
                    "/reference/",
                ],
                "max_match_rank": 3,
                "pass_reason": "top 3 include the main React docs entry points",
                "fail_reason": "top 3 do not include the main React docs entry points",
            }
        },
        known_domains=["react.dev"],
    )

    assert status == "fail"
    assert reason == "top 3 do not include the main React docs entry points"


def test_term_rule_can_require_title_terms_and_rank_window():
    case = CanonicalEvalCase(
        query="Python 3.13 release",
        query_type="news/reference",
        expected="docs.python.org release notes",
        notes="Official release page should be in top 3",
    )
    payload = {
        "total": 3,
        "hits": [
            {
                "url": "https://docs.python.org/3/using/windows.html",
                "title": "Using Python on Windows",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://docs.python.org/3/library/py_compile.html",
                "title": "py_compile",
                "snip": "",
                "snip_plain": "",
            },
            {
                "url": "https://docs.python.org/3.13/whatsnew/3.13.html",
                "title": "What's New in Python 3.13",
                "snip": "",
                "snip_plain": "",
            },
        ],
    }

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={
            "python 3.13 release": {
                "required_domains": ["docs.python.org"],
                "required_title_terms": ["python 3.13"],
                "required_path_terms": ["/whatsnew/3.13.html"],
                "max_match_rank": 3,
                "pass_reason": "top 3 include the official Python 3.13 release notes",
                "fail_reason": "top 3 do not include the official Python 3.13 release notes",
            }
        },
        known_domains=["docs.python.org"],
    )

    assert status == "pass"
    assert reason == "top 3 include the official Python 3.13 release notes"


def test_comparison_term_rule_rejects_non_comparison_mentions():
    case = CanonicalEvalCase(
        query="FastAPI vs Django",
        query_type="comparison",
        expected="a page that explicitly compares FastAPI and Django",
        notes="Top 3 should include a result that names both FastAPI and Django",
    )
    payload = {
        "total": 3,
        "hits": [
            {
                "url": "https://fastapi.tiangolo.com/",
                "title": "FastAPI",
                "snip": "",
                "snip_plain": "FastAPI framework, high performance, easy to learn.",
            },
            {
                "url": "https://fastapi.tiangolo.com/zh/",
                "title": "FastAPI",
                "snip": "",
                "snip_plain": "FastAPI documentation in Chinese.",
            },
            {
                "url": "https://forum.djangoproject.com/t/looking-for-examples",
                "title": "Looking for examples of OSS Django projects as PyPI packages",
                "snip": "",
                "snip_plain": "I am more comfortable with Django than other tools like FastAPI.",
            },
        ],
    }

    status, reason = module._classify_case(
        case,
        payload,
        keyword_rules={
            "fastapi vs django": {
                "required_terms": ["fastapi", "django"],
                "any_of_terms": [" vs ", "versus", "compare", "comparison"],
                "required_title_terms": ["fastapi", "django"],
                "pass_reason": "top 3 include an explicit FastAPI and Django comparison",
                "fail_reason": "top 3 do not include an explicit FastAPI and Django comparison",
            }
        },
        known_domains=[],
    )

    assert status == "fail"
    assert reason == "top 3 do not include an explicit FastAPI and Django comparison"


def test_load_config_merges_canonical_query_cases(tmp_path):
    config_path = tmp_path / "search_eval_cases.json"
    config_path.write_text(
        json.dumps(
            {
                "known_domains": [],
                "query_keyword_rules": {},
                "query_cases": [
                    {
                        "query": "Example query",
                        "query_type": "reference",
                        "expected": "example.com",
                        "notes": "Example local case",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, keyword_rules, known_domains = module._load_config(config_path)
    query_names = {case.query for case in cases}

    assert "React docs" in query_names
    assert "Example query" in query_names
    assert "react docs" in keyword_rules
    assert "react.dev" in known_domains


def test_load_config_reads_optional_judgments(tmp_path):
    config_path = tmp_path / "search_eval_cases.json"
    config_path.write_text(
        json.dumps(
            {
                "known_domains": ["docs.example.com"],
                "query_keyword_rules": {},
                "query_cases": [
                    {
                        "query": "Example docs",
                        "query_type": "reference",
                        "expected": "docs.example.com",
                        "notes": "Example local case",
                        "judgments": [
                            {
                                "relevance": 3,
                                "domain": "docs.example.com",
                                "path_prefix": "/guide",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, _, _ = module._load_config(config_path)
    case = next(case for case in cases if case.query == "Example docs")

    assert len(case.judgments) == 1
    assert case.judgments[0].relevance == 3
    assert case.judgments[0].domain == "docs.example.com"


def test_main_writes_json_report(monkeypatch, tmp_path):
    output_path = tmp_path / "report.json"
    case = CanonicalEvalCase(
        query="Example docs",
        query_type="reference",
        expected="docs.example.com",
        notes="Example local case",
    )

    def _fake_fetch_results(base_url: str, query: str, limit: int) -> dict:
        assert base_url == "https://example.test"
        assert query == "Example docs"
        assert limit == 3
        return {
            "total": 2,
            "mode": "test",
            "hits": [
                {
                    "url": "https://docs.example.com/guide/getting-started",
                    "title": "Getting Started",
                    "snip": "",
                    "snip_plain": "",
                },
                {
                    "url": "https://blog.example.com/post",
                    "title": "Post",
                    "snip": "",
                    "snip_plain": "",
                },
            ],
        }

    def _fake_load_config(_config_path):
        return [case], {}, ["docs.example.com"]

    monkeypatch.setattr(module, "_load_config", _fake_load_config)
    monkeypatch.setattr(module, "_fetch_results", _fake_fetch_results)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            "--base-url",
            "https://example.test",
            "--config",
            str(tmp_path / "search_eval_cases.json"),
            "--json-output",
            str(output_path),
        ],
    )

    exit_code = module.main()
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["counts"]["matched"] == 1
    assert report["match_rate"] == 1.0
    assert report["cases"][0]["outcome"] == "matched"
    assert report["cases"][0]["target"] == "docs.example.com"
    assert report["cases"][0]["metrics"]["hit_at_1"] == 1.0
    assert report["cases"][0]["metrics"]["bad_at_3"] == 0.0
    assert report["cases"][0]["top_hits"][0]["relevance"] == 3


def test_main_reports_case_misses_without_nonzero_exit(monkeypatch, tmp_path):
    case = CanonicalEvalCase(
        query="Example docs",
        query_type="reference",
        expected="docs.example.com",
        notes="Example docs should be in top 3",
    )

    def _fake_fetch_results(_base_url: str, _query: str, _limit: int) -> dict:
        return {"total": 0, "mode": "test", "hits": []}

    def _fake_load_config(_config_path):
        return [case], {}, ["docs.example.com"]

    monkeypatch.setattr(module, "_load_config", _fake_load_config)
    monkeypatch.setattr(module, "_fetch_results", _fake_fetch_results)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            "--base-url",
            "https://example.test",
            "--config",
            str(tmp_path / "search_eval_cases.json"),
        ],
    )

    assert module.main() == 0


def test_main_includes_misses_in_full_report(monkeypatch, tmp_path):
    case = CanonicalEvalCase(
        query="Example comparison",
        query_type="comparison",
        expected="a useful comparison",
        notes="Example visibility case",
    )

    def _fake_fetch_results(_base_url: str, _query: str, _limit: int) -> dict:
        return {"total": 0, "mode": "test", "hits": []}

    def _fake_load_config(_config_path):
        return [case], {}, []

    monkeypatch.setattr(module, "_load_config", _fake_load_config)
    monkeypatch.setattr(module, "_fetch_results", _fake_fetch_results)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            "--base-url",
            "https://example.test",
            "--config",
            str(tmp_path / "search_eval_cases.json"),
            "--json-output",
            str(tmp_path / "report.json"),
        ],
    )

    assert module.main() == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["counts"]["missed"] == 1
    assert report["match_rate"] == 0.0
    assert report["cases"][0]["outcome"] == "missed"
    assert report["cases"][0]["observation"] == "0 hits"
    assert report["cases"][0]["target"] == "a useful comparison"
