"""Canonical source manifest loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

CanonicalQueryClass = Literal[
    "navigational", "reference", "news", "comparison", "other"
]

CANONICAL_SOURCES_FILENAME = "canonical_sources.json"


def _candidate_manifest_paths() -> tuple[Path, ...]:
    return (
        Path(__file__).resolve().parents[5] / "config" / CANONICAL_SOURCES_FILENAME,
        Path.cwd() / "config" / CANONICAL_SOURCES_FILENAME,
    )


def _resolve_manifest_path() -> Path:
    for path in _candidate_manifest_paths():
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not find {CANONICAL_SOURCES_FILENAME} in any known config path"
    )


@dataclass(frozen=True)
class EvalJudgment:
    relevance: int
    url: str | None = None
    domain: str | None = None
    path_prefix: str | None = None
    title_terms: tuple[str, ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class CanonicalEvalCase:
    query: str
    query_type: str
    expected: str
    notes: str
    required_terms: tuple[str, ...] = ()
    required_domains: tuple[str, ...] = ()
    minimum_domain_matches: int = 1
    any_of_terms: tuple[str, ...] = ()
    required_title_terms: tuple[str, ...] = ()
    required_paths: tuple[str, ...] = ()
    required_path_terms: tuple[str, ...] = ()
    excluded_domains: tuple[str, ...] = ()
    max_match_rank: int | None = None
    pass_reason: str | None = None
    fail_reason: str | None = None
    judgments: tuple[EvalJudgment, ...] = ()

    @property
    def query_key(self) -> str:
        return self.query.strip().lower()

    @property
    def has_explicit_rule(self) -> bool:
        return bool(self.required_terms or self.required_domains)


@dataclass(frozen=True)
class CanonicalSourceConfig:
    key: str
    aliases: tuple[str, ...]
    domains: tuple[str, ...]
    preferred_paths: tuple[str, ...] = ()
    news_paths: tuple[str, ...] = ()
    default_class: CanonicalQueryClass = "reference"
    candidate_window: int = 20
    retrieval_query: str | None = None
    restrict_to_source: bool = False
    cases: tuple[CanonicalEvalCase, ...] = ()


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tuple_of_strings(values: list[str] | None) -> tuple[str, ...]:
    return tuple(value for value in (values or []) if value)


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_string_list(values: object, field_name: str) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")


def _validate_case(item: dict, *, source_key: str, case_index: int) -> None:
    prefix = f"sources[{source_key}].cases[{case_index}]"
    _require_non_empty_string(item.get("query"), f"{prefix}.query")
    _require_non_empty_string(item.get("query_type"), f"{prefix}.query_type")
    _require_non_empty_string(item.get("expected"), f"{prefix}.expected")
    _require_non_empty_string(item.get("notes"), f"{prefix}.notes")

    required_terms = item.get("required_terms")
    required_domains = item.get("required_domains")
    any_of_terms = item.get("any_of_terms")
    required_title_terms = item.get("required_title_terms")
    required_paths = item.get("required_paths")
    required_path_terms = item.get("required_path_terms")
    excluded_domains = item.get("excluded_domains")

    for field_name, values in (
        ("required_terms", required_terms),
        ("required_domains", required_domains),
        ("any_of_terms", any_of_terms),
        ("required_title_terms", required_title_terms),
        ("required_paths", required_paths),
        ("required_path_terms", required_path_terms),
        ("excluded_domains", excluded_domains),
    ):
        _validate_string_list(values, f"{prefix}.{field_name}")

    if required_terms and required_domains:
        raise ValueError(
            f"{prefix} must not define both required_terms and required_domains"
        )

    if any_of_terms and not required_terms:
        raise ValueError(f"{prefix}.any_of_terms requires required_terms")

    if any(
        (
            required_title_terms,
            required_paths,
            required_path_terms,
            excluded_domains,
        )
    ) and not (required_terms or required_domains):
        raise ValueError(
            f"{prefix} title/path/domain filters require required_terms or required_domains"
        )

    minimum_domain_matches = item.get("minimum_domain_matches")
    if minimum_domain_matches is not None and (
        not isinstance(minimum_domain_matches, int) or minimum_domain_matches < 1
    ):
        raise ValueError(f"{prefix}.minimum_domain_matches must be a positive integer")

    if (
        required_domains
        and minimum_domain_matches is not None
        and minimum_domain_matches > len(required_domains)
    ):
        raise ValueError(
            f"{prefix}.minimum_domain_matches exceeds required_domains length"
        )

    max_match_rank = item.get("max_match_rank")
    if max_match_rank is not None and (
        not isinstance(max_match_rank, int) or max_match_rank < 1
    ):
        raise ValueError(f"{prefix}.max_match_rank must be a positive integer")

    has_explicit_rule = bool(required_terms or required_domains)
    if has_explicit_rule:
        _require_non_empty_string(item.get("pass_reason"), f"{prefix}.pass_reason")
        _require_non_empty_string(item.get("fail_reason"), f"{prefix}.fail_reason")

    judgments = item.get("judgments")
    if judgments is None:
        return
    if not isinstance(judgments, list):
        raise ValueError(f"{prefix}.judgments must be a list")
    for judgment_index, judgment in enumerate(judgments, start=1):
        judgment_prefix = f"{prefix}.judgments[{judgment_index}]"
        if not isinstance(judgment, dict):
            raise ValueError(f"{judgment_prefix} must be an object")
        relevance = judgment.get("relevance")
        if not isinstance(relevance, int) or relevance < -1 or relevance > 3:
            raise ValueError(f"{judgment_prefix}.relevance must be an integer in -1..3")
        if judgment.get("url") is not None:
            _require_non_empty_string(judgment.get("url"), f"{judgment_prefix}.url")
        if judgment.get("domain") is not None:
            _require_non_empty_string(
                judgment.get("domain"), f"{judgment_prefix}.domain"
            )
        if judgment.get("path_prefix") is not None:
            _require_non_empty_string(
                judgment.get("path_prefix"), f"{judgment_prefix}.path_prefix"
            )
        _validate_string_list(
            judgment.get("title_terms"), f"{judgment_prefix}.title_terms"
        )
        if not any(
            judgment.get(field)
            for field in ("url", "domain", "path_prefix", "title_terms")
        ):
            raise ValueError(
                f"{judgment_prefix} must define url, domain, path_prefix, or title_terms"
            )


def _load_judgment(item: dict) -> EvalJudgment:
    title_terms = item.get("title_terms") or []
    return EvalJudgment(
        relevance=int(item["relevance"]),
        url=item.get("url"),
        domain=item.get("domain"),
        path_prefix=item.get("path_prefix"),
        title_terms=_tuple_of_strings(title_terms),
        notes=item.get("notes"),
    )


def _derive_case_judgments(
    *,
    query_type: str,
    source_domains: tuple[str, ...],
    source_preferred_paths: tuple[str, ...],
    source_news_paths: tuple[str, ...],
) -> tuple[EvalJudgment, ...]:
    judgments: list[EvalJudgment] = []

    preferred_paths = source_preferred_paths
    if "news" in query_type and source_news_paths:
        preferred_paths = source_news_paths

    if preferred_paths:
        for domain in source_domains:
            for path_prefix in preferred_paths:
                judgments.append(
                    EvalJudgment(
                        relevance=3,
                        domain=domain,
                        path_prefix=path_prefix,
                        notes="derived preferred path",
                    )
                )
        for domain in source_domains:
            judgments.append(
                EvalJudgment(
                    relevance=2,
                    domain=domain,
                    notes="derived source domain",
                )
            )
        return tuple(judgments)

    for domain in source_domains:
        judgments.append(
            EvalJudgment(
                relevance=3,
                domain=domain,
                notes="derived source domain",
            )
        )
    return tuple(judgments)


def _validate_source(item: dict, *, source_index: int) -> None:
    source_key = _require_non_empty_string(
        item.get("key"), f"sources[{source_index}].key"
    )

    _validate_string_list(item.get("aliases"), f"sources[{source_index}].aliases")
    _validate_string_list(item.get("domains"), f"sources[{source_index}].domains")
    _validate_string_list(
        item.get("preferred_paths"), f"sources[{source_index}].preferred_paths"
    )
    _validate_string_list(item.get("news_paths"), f"sources[{source_index}].news_paths")

    aliases = item.get("aliases") or []
    domains = item.get("domains") or []
    if not aliases:
        raise ValueError(f"sources[{source_key}].aliases must not be empty")
    if not domains:
        raise ValueError(f"sources[{source_key}].domains must not be empty")

    default_class = item.get("default_class", "reference")
    if default_class not in {
        "navigational",
        "reference",
        "news",
        "comparison",
        "other",
    }:
        raise ValueError(f"sources[{source_key}].default_class is invalid")

    candidate_window = item.get("candidate_window")
    if candidate_window is not None and (
        not isinstance(candidate_window, int) or candidate_window < 1
    ):
        raise ValueError(f"sources[{source_key}].candidate_window must be positive")

    retrieval_query = item.get("retrieval_query")
    if retrieval_query is not None:
        _require_non_empty_string(
            retrieval_query, f"sources[{source_key}].retrieval_query"
        )

    cases = item.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"sources[{source_key}].cases must be a non-empty list")

    seen_queries: set[str] = set()
    for case_index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(
                f"sources[{source_key}].cases[{case_index}] must be an object"
            )
        _validate_case(case, source_key=source_key, case_index=case_index)
        query_key = case["query"].strip().lower()
        if query_key in seen_queries:
            raise ValueError(
                f"sources[{source_key}] contains duplicate case query: {case['query']}"
            )
        seen_queries.add(query_key)


def _validate_manifest(raw: dict) -> None:
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a non-empty list")

    seen_keys: set[str] = set()
    for source_index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"sources[{source_index}] must be an object")
        source_key = _require_non_empty_string(
            source.get("key"), f"sources[{source_index}].key"
        )
        if source_key in seen_keys:
            raise ValueError(f"sources contains duplicate key: {source_key}")
        seen_keys.add(source_key)
        _validate_source(source, source_index=source_index)


def _load_case(
    item: dict,
    *,
    source_domains: tuple[str, ...],
    source_preferred_paths: tuple[str, ...],
    source_news_paths: tuple[str, ...],
) -> CanonicalEvalCase:
    configured_judgments = tuple(
        _load_judgment(row) for row in item.get("judgments", [])
    )
    return CanonicalEvalCase(
        query=item["query"],
        query_type=item["query_type"],
        expected=item["expected"],
        notes=item["notes"],
        required_terms=_tuple_of_strings(item.get("required_terms")),
        required_domains=_tuple_of_strings(item.get("required_domains")),
        minimum_domain_matches=int(item.get("minimum_domain_matches") or 1),
        any_of_terms=_tuple_of_strings(item.get("any_of_terms")),
        required_title_terms=_tuple_of_strings(item.get("required_title_terms")),
        required_paths=_tuple_of_strings(item.get("required_paths")),
        required_path_terms=_tuple_of_strings(item.get("required_path_terms")),
        excluded_domains=_tuple_of_strings(item.get("excluded_domains")),
        max_match_rank=(
            int(item["max_match_rank"])
            if item.get("max_match_rank") is not None
            else None
        ),
        pass_reason=item.get("pass_reason"),
        fail_reason=item.get("fail_reason"),
        judgments=configured_judgments
        or _derive_case_judgments(
            query_type=item["query_type"],
            source_domains=source_domains,
            source_preferred_paths=source_preferred_paths,
            source_news_paths=source_news_paths,
        ),
    )


@lru_cache(maxsize=1)
def load_canonical_source_configs() -> tuple[CanonicalSourceConfig, ...]:
    raw = _load_manifest(_resolve_manifest_path())
    _validate_manifest(raw)
    configs: list[CanonicalSourceConfig] = []
    for item in raw.get("sources", []):
        domains = _tuple_of_strings(item.get("domains"))
        preferred_paths = _tuple_of_strings(item.get("preferred_paths"))
        news_paths = _tuple_of_strings(item.get("news_paths"))
        cases = tuple(
            _load_case(
                case,
                source_domains=domains,
                source_preferred_paths=preferred_paths,
                source_news_paths=news_paths,
            )
            for case in item.get("cases", [])
        )
        configs.append(
            CanonicalSourceConfig(
                key=item["key"],
                aliases=_tuple_of_strings(item.get("aliases")),
                domains=domains,
                preferred_paths=preferred_paths,
                news_paths=news_paths,
                default_class=item.get("default_class", "reference"),
                candidate_window=int(item.get("candidate_window") or 20),
                retrieval_query=item.get("retrieval_query"),
                restrict_to_source=bool(item.get("restrict_to_source")),
                cases=cases,
            )
        )
    return tuple(configs)


def canonical_eval_keyword_rules() -> dict[str, dict]:
    rules: dict[str, dict] = {}
    for source in load_canonical_source_configs():
        for case in source.cases:
            if not case.has_explicit_rule:
                continue
            payload: dict[str, object] = {
                "pass_reason": case.pass_reason or "",
                "fail_reason": case.fail_reason or "",
            }
            if case.required_terms:
                payload["required_terms"] = list(case.required_terms)
            if case.required_domains:
                payload["required_domains"] = list(case.required_domains)
                payload["minimum_domain_matches"] = case.minimum_domain_matches
            if case.any_of_terms:
                payload["any_of_terms"] = list(case.any_of_terms)
            if case.required_title_terms:
                payload["required_title_terms"] = list(case.required_title_terms)
            if case.required_paths:
                payload["required_paths"] = list(case.required_paths)
            if case.required_path_terms:
                payload["required_path_terms"] = list(case.required_path_terms)
            if case.excluded_domains:
                payload["excluded_domains"] = list(case.excluded_domains)
            if case.max_match_rank is not None:
                payload["max_match_rank"] = case.max_match_rank
            rules[case.query_key] = payload
    return rules


def canonical_known_domains() -> list[str]:
    domains: set[str] = set()
    for source in load_canonical_source_configs():
        domains.update(source.domains)
        for case in source.cases:
            domains.update(case.required_domains)
            domains.update(case.excluded_domains)
    return sorted(domains, key=len, reverse=True)


def canonical_query_cases() -> list[CanonicalEvalCase]:
    cases: list[CanonicalEvalCase] = []
    seen: set[str] = set()
    for source in load_canonical_source_configs():
        for case in source.cases:
            if case.query_key in seen:
                continue
            seen.add(case.query_key)
            cases.append(case)
    return cases
