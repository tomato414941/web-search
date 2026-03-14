from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_eval_script():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "ops" / "evaluate_search.py"
    )
    spec = spec_from_file_location("evaluate_search_script", script_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_domain_prefers_longest_known_domain_match():
    module = _load_eval_script()

    domain = module._extract_domain(
        "docs.github.com",
        ["github.com", "docs.github.com"],
    )

    assert domain == "docs.github.com"


def test_reference_case_requires_expected_docs_subdomain():
    module = _load_eval_script()
    case = module.QueryCase(
        query="GitHub docs",
        query_type="reference",
        expected="docs.github.com",
        notes="Official GitHub docs should be in top 3",
        tier=1,
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


def test_domain_rule_respects_excluded_domains():
    module = _load_eval_script()
    case = module.QueryCase(
        query="OpenAI announcements",
        query_type="news/reference",
        expected="official OpenAI announcements",
        notes="Top 3 should include an official OpenAI announcements page",
        tier=2,
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


def test_domain_rule_can_require_exact_paths_and_rank_window():
    module = _load_eval_script()
    case = module.QueryCase(
        query="React docs",
        query_type="reference",
        expected="react.dev",
        notes="Official React docs should be in top 3",
        tier=1,
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
    module = _load_eval_script()
    case = module.QueryCase(
        query="Python 3.13 release",
        query_type="news/reference",
        expected="docs.python.org release notes",
        notes="Official release page should rank high",
        tier=1,
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
                "max_match_rank": 2,
                "pass_reason": "top 2 include the official Python 3.13 release notes",
                "fail_reason": "top 2 do not include the official Python 3.13 release notes",
            }
        },
        known_domains=["docs.python.org"],
    )

    assert status == "fail"
    assert reason == "top 2 do not include the official Python 3.13 release notes"
