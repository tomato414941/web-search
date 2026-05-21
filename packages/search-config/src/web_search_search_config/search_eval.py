"""Search evaluation config helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from web_search_search_config.canonical_sources import (
    CanonicalEvalCase,
    EvalJudgment,
    canonical_eval_keyword_rules,
    canonical_known_domains,
    canonical_query_cases,
)


@dataclass(frozen=True)
class SearchEvalConfig:
    query_cases: tuple[CanonicalEvalCase, ...]
    keyword_rules: dict[str, dict]
    known_domains: tuple[str, ...]


def load_local_search_eval_config(path: Path) -> SearchEvalConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    query_cases = tuple(
        CanonicalEvalCase(
            query=case["query"],
            query_type=case["query_type"],
            expected=case["expected"],
            notes=case["notes"],
            judgments=tuple(
                EvalJudgment(
                    relevance=int(judgment["relevance"]),
                    url=judgment.get("url"),
                    domain=judgment.get("domain"),
                    path_prefix=judgment.get("path_prefix"),
                    title_terms=tuple(judgment.get("title_terms", ())),
                    notes=judgment.get("notes"),
                )
                for judgment in case.get("judgments", [])
            ),
        )
        for case in raw.get("query_cases", [])
    )
    keyword_rules = dict(raw.get("query_keyword_rules", {}))
    known_domains = tuple(raw.get("known_domains", []))
    return SearchEvalConfig(
        query_cases=query_cases,
        keyword_rules=keyword_rules,
        known_domains=known_domains,
    )


def canonical_search_eval_config() -> SearchEvalConfig:
    return SearchEvalConfig(
        query_cases=tuple(canonical_query_cases()),
        keyword_rules=canonical_eval_keyword_rules(),
        known_domains=tuple(canonical_known_domains()),
    )


def merge_search_eval_configs(*configs: SearchEvalConfig) -> SearchEvalConfig:
    query_cases: list[CanonicalEvalCase] = []
    seen_queries: set[str] = set()
    keyword_rules: dict[str, dict] = {}
    known_domains: set[str] = set()

    for config in configs:
        for case in config.query_cases:
            if case.query_key in seen_queries:
                continue
            seen_queries.add(case.query_key)
            query_cases.append(case)
        keyword_rules.update(config.keyword_rules)
        known_domains.update(domain.lower() for domain in config.known_domains)

    return SearchEvalConfig(
        query_cases=tuple(query_cases),
        keyword_rules=keyword_rules,
        known_domains=tuple(sorted(known_domains, key=len, reverse=True)),
    )


def load_merged_search_eval_config(path: Path) -> SearchEvalConfig:
    return merge_search_eval_configs(
        canonical_search_eval_config(),
        load_local_search_eval_config(path),
    )
