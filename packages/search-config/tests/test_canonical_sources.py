import pytest

from web_search_search_config import canonical_sources as canonical_sources_module
from web_search_search_config.canonical_sources import (
    _validate_manifest,
    canonical_eval_keyword_rules,
    canonical_known_domains,
    canonical_query_cases,
    load_canonical_source_configs,
)
from web_search_search_config.search_eval import (
    canonical_search_eval_config,
    merge_search_eval_configs,
)


def test_load_canonical_source_configs_includes_python_release_notes():
    sources = {source.key: source for source in load_canonical_source_configs()}

    assert "python_release_notes" in sources
    assert "site_reliability_engineering" in sources
    assert "docs.python.org" in sources["python_release_notes"].domains
    assert "sre.google" in sources["site_reliability_engineering"].domains
    assert sources["python_release_notes"].restrict_to_source is True
    assert "google" in sources
    assert "openai_api" in sources
    assert "docker_docs" in sources
    assert "pytest_docs" in sources


def test_canonical_eval_keyword_rules_include_react_docs():
    rules = canonical_eval_keyword_rules()

    assert "react docs" in rules
    assert rules["react docs"]["required_domains"] == ["react.dev"]


def test_canonical_known_domains_include_openai_and_python_docs():
    domains = set(canonical_known_domains())

    assert "openai.com" in domains
    assert "docs.python.org" in domains


def test_canonical_query_cases_include_react_docs():
    cases = {case.query: case for case in canonical_query_cases()}

    assert "React docs" in cases
    assert "site reliability engineering" in cases
    assert cases["React docs"].query_type == "reference"


def test_canonical_query_cases_include_openai_news_cases():
    cases = {case.query: case for case in canonical_query_cases()}

    assert cases["OpenAI news"].query_type == "news/reference"
    assert cases["OpenAI announcements"].query_type == "news/reference"


def test_canonical_query_cases_include_news_reference_constraints():
    cases = {case.query: case for case in canonical_query_cases()}

    assert cases["Python 3.13 release"].max_match_rank == 3


def test_reference_cases_use_specific_path_constraints():
    cases = {case.query: case for case in canonical_query_cases()}
    constrained_cases = {
        "GitHub Actions": ("github.com", "/actions"),
        "Docker compose file reference": ("docs.docker.com", "/compose/compose-file"),
        "Django model field reference": (
            "docs.djangoproject.com",
            "/ref/models/fields",
        ),
        "pytest fixture": ("docs.pytest.org", "fixtures"),
        "pytest markers": ("docs.pytest.org", "markers"),
        "pytest parametrize": ("docs.pytest.org", "parametrize"),
    }

    for query, (domain, path_term) in constrained_cases.items():
        case = cases[query]
        assert domain in case.required_domains
        assert path_term in case.required_path_terms
        assert case.max_match_rank == 3


def test_canonical_query_cases_drive_eval_rules():
    config = canonical_search_eval_config()
    case = {case.query: case for case in config.query_cases}["React docs"]

    assert case.has_explicit_rule is True
    assert config.keyword_rules["react docs"]["required_domains"] == ["react.dev"]


def test_merge_search_eval_configs_dedupes_query_cases_by_query():
    config = canonical_search_eval_config()
    merged = merge_search_eval_configs(config, config)

    assert len(merged.query_cases) == len(config.query_cases)


def test_validate_manifest_rejects_duplicate_case_queries():
    raw = {
        "sources": [
            {
                "key": "dup",
                "aliases": ["dup"],
                "domains": ["example.com"],
                "cases": [
                    {
                        "query": "Example",
                        "query_type": "reference",
                        "expected": "example.com",
                        "notes": "x",
                    },
                    {
                        "query": "Example",
                        "query_type": "reference",
                        "expected": "example.com",
                        "notes": "x",
                    },
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match="duplicate case query"):
        _validate_manifest(raw)


def test_validate_manifest_rejects_mixed_required_terms_and_domains():
    raw = {
        "sources": [
            {
                "key": "bad-rule",
                "aliases": ["bad rule"],
                "domains": ["example.com"],
                "cases": [
                    {
                        "query": "Bad rule",
                        "query_type": "reference",
                        "expected": "example.com",
                        "notes": "x",
                        "required_terms": ["bad"],
                        "required_domains": ["example.com"],
                        "pass_reason": "x",
                        "fail_reason": "y",
                    }
                ],
            }
        ]
    }

    with pytest.raises(
        ValueError, match="must not define both required_terms and required_domains"
    ):
        _validate_manifest(raw)


def test_resolve_manifest_path_falls_back_to_existing_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    manifest_path = tmp_path / "config" / "canonical_sources.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text('{"sources": []}', encoding="utf-8")

    monkeypatch.setattr(
        canonical_sources_module,
        "_candidate_manifest_paths",
        lambda: (tmp_path / "missing.json", manifest_path),
    )

    assert canonical_sources_module._resolve_manifest_path() == manifest_path


def test_resolve_manifest_path_raises_when_manifest_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(
        canonical_sources_module,
        "_candidate_manifest_paths",
        lambda: (tmp_path / "missing.json",),
    )

    with pytest.raises(FileNotFoundError, match="canonical_sources.json"):
        canonical_sources_module._resolve_manifest_path()
