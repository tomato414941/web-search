#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


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

        tier = case.get("tier")
        if tier not in (1, 2):
            errors.append(f"query_cases[{index}].tier must be 1 or 2: {query}")

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

        if (required_path_terms or excluded_domains) and not required_domains:
            errors.append(
                f"query_keyword_rules[{query_key}] path/domain filters require required_domains"
            )

        for field_name, values in (
            ("required_terms", required_terms),
            ("required_domains", required_domains),
            ("any_of_terms", any_of_terms),
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate search evaluation config.")
    parser.add_argument(
        "--config",
        default="config/search_eval_cases.json",
        help="Path to the evaluation config JSON file",
    )
    args = parser.parse_args()

    raw = _load_config(Path(args.config))
    errors: list[str] = []

    known_domains = raw.get("known_domains")
    if not isinstance(known_domains, list) or not known_domains:
        errors.append("known_domains must be a non-empty list")
    else:
        _validate_known_domains(known_domains, errors)

    keyword_rules = raw.get("query_keyword_rules")
    if not isinstance(keyword_rules, dict):
        errors.append("query_keyword_rules must be an object")
        keyword_rules = {}
    else:
        _validate_keyword_rules(keyword_rules, errors)

    query_cases = raw.get("query_cases")
    if not isinstance(query_cases, list) or not query_cases:
        errors.append("query_cases must be a non-empty list")
    else:
        _validate_query_cases(query_cases, keyword_rules, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("OK: search evaluation config is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
