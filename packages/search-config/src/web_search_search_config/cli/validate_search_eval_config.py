import argparse
import json
from pathlib import Path

from web_search_search_config.search_eval import (
    canonical_search_eval_config,
    load_local_search_eval_config,
    merge_search_eval_configs,
)


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_known_domains(known_domains: list[str], errors: list[str]) -> None:
    seen: set[str] = set()
    for index, domain in enumerate(known_domains, start=1):
        if not isinstance(domain, str) or not domain.strip():
            errors.append(f"known_domains[{index}] must be a non-empty string")
            continue
        normalized = domain.strip().lower()
        if normalized != domain:
            errors.append(f"known_domains[{index}] must already be lowercase: {domain}")
        if normalized in seen:
            errors.append(f"known_domains contains a duplicate: {domain}")
            continue
        seen.add(normalized)


def _validate_query_cases(
    query_cases: list[dict],
    keyword_rules: dict[str, dict],
    errors: list[str],
) -> None:
    seen_queries: set[str] = set()
    query_keys: set[str] = set()

    for index, case in enumerate(query_cases, start=1):
        query = case.get("query")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"query_cases[{index}].query must be a non-empty string")
            continue
        query = query.strip()
        query_key = query.lower()
        if query_key in seen_queries:
            errors.append(f"query_cases contains duplicate query: {query}")
        seen_queries.add(query_key)
        query_keys.add(query_key)

        for field in ("query_type", "expected", "notes"):
            value = case.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"query_cases[{index}].{field} must be a non-empty string"
                )

        judgments = case.get("judgments")
        if judgments is not None:
            if not isinstance(judgments, list):
                errors.append(f"query_cases[{index}].judgments must be a list")
            else:
                for judgment_index, judgment in enumerate(judgments, start=1):
                    prefix = f"query_cases[{index}].judgments[{judgment_index}]"
                    if not isinstance(judgment, dict):
                        errors.append(f"{prefix} must be an object")
                        continue
                    relevance = judgment.get("relevance")
                    if (
                        not isinstance(relevance, int)
                        or relevance < -1
                        or relevance > 3
                    ):
                        errors.append(f"{prefix}.relevance must be an integer in -1..3")
                    for field in ("url", "domain", "path_prefix", "notes"):
                        value = judgment.get(field)
                        if value is not None and (
                            not isinstance(value, str) or not value.strip()
                        ):
                            errors.append(
                                f"{prefix}.{field} must be a non-empty string when provided"
                            )
                    title_terms = judgment.get("title_terms") or []
                    if title_terms and (
                        not isinstance(title_terms, list)
                        or not all(
                            isinstance(value, str) and value.strip()
                            for value in title_terms
                        )
                    ):
                        errors.append(
                            f"{prefix}.title_terms must contain only non-empty strings"
                        )
                    if not any(
                        judgment.get(field)
                        for field in ("url", "domain", "path_prefix", "title_terms")
                    ):
                        errors.append(
                            f"{prefix} must define url, domain, path_prefix, or title_terms"
                        )

    for rule_key in keyword_rules:
        if rule_key not in query_keys:
            errors.append(f"query_keyword_rules has no matching query: {rule_key}")


def _validate_keyword_rules(
    keyword_rules: dict[str, dict],
    errors: list[str],
) -> None:
    for query_key, rule in keyword_rules.items():
        if not isinstance(rule, dict):
            errors.append(f"query_keyword_rules[{query_key}] must be an object")
            continue

        for field in ("pass_reason", "fail_reason"):
            value = rule.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"query_keyword_rules[{query_key}].{field} must be a non-empty string"
                )

        required_terms = rule.get("required_terms") or []
        required_domains = rule.get("required_domains") or []
        any_of_terms = rule.get("any_of_terms") or []
        required_title_terms = rule.get("required_title_terms") or []
        required_paths = rule.get("required_paths") or []
        required_path_terms = rule.get("required_path_terms") or []
        excluded_domains = rule.get("excluded_domains") or []

        if not required_terms and not required_domains:
            errors.append(
                f"query_keyword_rules[{query_key}] must define required_terms or required_domains"
            )

        if required_terms and required_domains:
            errors.append(
                f"query_keyword_rules[{query_key}] must not mix required_terms and required_domains"
            )

        if any_of_terms and not required_terms:
            errors.append(
                f"query_keyword_rules[{query_key}].any_of_terms requires required_terms"
            )

        if (
            required_title_terms
            or required_paths
            or required_path_terms
            or excluded_domains
        ) and not (required_domains or required_terms):
            errors.append(
                f"query_keyword_rules[{query_key}] title/path/domain filters require required_domains or required_terms"
            )

        for field_name, values in (
            ("required_terms", required_terms),
            ("required_domains", required_domains),
            ("any_of_terms", any_of_terms),
            ("required_title_terms", required_title_terms),
            ("required_paths", required_paths),
            ("required_path_terms", required_path_terms),
            ("excluded_domains", excluded_domains),
        ):
            if not isinstance(values, list):
                errors.append(
                    f"query_keyword_rules[{query_key}].{field_name} must be a list"
                )
                continue
            if values and not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                errors.append(
                    f"query_keyword_rules[{query_key}].{field_name} must contain only non-empty strings"
                )

        minimum_matches = rule.get("minimum_domain_matches")
        if minimum_matches is not None:
            if not isinstance(minimum_matches, int) or minimum_matches < 1:
                errors.append(
                    f"query_keyword_rules[{query_key}].minimum_domain_matches must be a positive integer"
                )
            elif required_domains and minimum_matches > len(required_domains):
                errors.append(
                    f"query_keyword_rules[{query_key}].minimum_domain_matches exceeds required_domains"
                )

        max_match_rank = rule.get("max_match_rank")
        if max_match_rank is not None and (
            not isinstance(max_match_rank, int) or max_match_rank < 1
        ):
            errors.append(
                f"query_keyword_rules[{query_key}].max_match_rank must be a positive integer"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate search evaluation config.")
    parser.add_argument(
        "--config",
        default="config/search_eval_cases.json",
        help="Path to the evaluation config JSON file",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    raw = _load_config(config_path)
    errors: list[str] = []

    keyword_rules = raw.get("query_keyword_rules")
    if not isinstance(keyword_rules, dict):
        errors.append("query_keyword_rules must be an object")
        keyword_rules = {}

    canonical_config = canonical_search_eval_config()
    manifest_query_keys = {case.query_key for case in canonical_config.query_cases}

    canonical_rules = canonical_config.keyword_rules
    duplicate_rule_keys = sorted(set(keyword_rules) & set(canonical_rules))
    for rule_key in duplicate_rule_keys:
        errors.append(
            f"query_keyword_rules[{rule_key}] duplicates canonical_sources.json"
        )

    local_config = load_local_search_eval_config(config_path)
    combined_config = merge_search_eval_configs(canonical_config, local_config)
    combined_keyword_rules = combined_config.keyword_rules
    _validate_keyword_rules(combined_keyword_rules, errors)

    query_cases = raw.get("query_cases")
    if not isinstance(query_cases, list):
        errors.append("query_cases must be a list")
    else:
        duplicate_query_keys = sorted(
            {case.get("query", "").strip().lower() for case in query_cases}
            & manifest_query_keys
        )
        for query_key in duplicate_query_keys:
            errors.append(f"query_cases[{query_key}] duplicates canonical_sources.json")

        combined_query_cases = [
            {
                "query": case.query,
                "query_type": case.query_type,
                "expected": case.expected,
                "notes": case.notes,
            }
            for case in combined_config.query_cases
        ]
        if not combined_query_cases:
            errors.append("combined query_cases must be non-empty")
        _validate_query_cases(combined_query_cases, combined_keyword_rules, errors)

    known_domains = raw.get("known_domains")
    if not isinstance(known_domains, list):
        errors.append("known_domains must be a list")
    else:
        merged_known_domains = list(combined_config.known_domains)
        if not merged_known_domains:
            errors.append("combined known_domains must be non-empty")
        _validate_known_domains(merged_known_domains, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("OK: search evaluation config is valid")
    return 0
