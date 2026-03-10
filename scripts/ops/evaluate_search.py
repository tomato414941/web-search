#!/usr/bin/env python3

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class QueryCase:
    query: str
    query_type: str
    expected: str
    notes: str
    tier: int


def _load_config(
    config_path: Path,
) -> tuple[list[QueryCase], dict[str, dict], list[str]]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    cases = [
        QueryCase(
            query=case["query"],
            query_type=case["query_type"],
            expected=case["expected"],
            notes=case["notes"],
            tier=int(case["tier"]),
        )
        for case in raw["query_cases"]
    ]
    if not cases:
        raise ValueError(f"No query cases found in {config_path}")
    keyword_rules = raw.get("query_keyword_rules", {})
    known_domains = [domain.lower() for domain in raw.get("known_domains", [])]
    return cases, keyword_rules, known_domains


def _fetch_results(base_url: str, query: str, limit: int) -> dict:
    encoded_query = urllib.parse.urlencode({"q": query, "limit": str(limit)})
    url = f"{base_url.rstrip('/')}/api/v1/search?{encoded_query}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pbs-search-eval/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_domain(text: str, known_domains: list[str]) -> str | None:
    match = re.search(r"`([^`]+)`", text)
    if match:
        return match.group(1).lower()

    lowered = text.lower()
    for domain in known_domains:
        if domain in lowered:
            return domain
    return None


def _normalize_url_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower()


def _normalize_url_path(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.path or "/"


def _hit_text(hit: dict) -> str:
    return " ".join(
        str(hit.get(field, "")) for field in ("title", "url", "snip_plain", "snip")
    ).lower()


def _domain_matches(
    expected_domain: str, actual_domain: str, *, allow_subdomain: bool
) -> bool:
    if actual_domain == expected_domain or actual_domain == f"www.{expected_domain}":
        return True
    if allow_subdomain and actual_domain.endswith(f".{expected_domain}"):
        return True
    return False


def _classify_case(
    case: QueryCase,
    payload: dict,
    *,
    keyword_rules: dict[str, dict],
    known_domains: list[str],
) -> tuple[str, str]:
    hits = payload.get("hits") or []
    total = int(payload.get("total") or 0)
    expected_domain = _extract_domain(case.expected, known_domains)
    top_urls = [hit.get("url", "") for hit in hits[:3]]
    top_domains = [_normalize_url_domain(url) for url in top_urls]
    top_paths = [_normalize_url_path(url) for url in top_urls]
    keyword_rule = keyword_rules.get(case.query.lower())

    if total == 0:
        return "fail", "0 hits"

    if keyword_rule:
        required_domains = keyword_rule.get("required_domains")
        minimum_domain_matches = int(keyword_rule.get("minimum_domain_matches") or 1)
        if required_domains:
            excluded_domains = tuple(keyword_rule.get("excluded_domains") or ())
            required_path_terms = tuple(keyword_rule.get("required_path_terms") or ())
            matches = sum(
                any(
                    _domain_matches(expected, domain, allow_subdomain=True)
                    for expected in required_domains
                )
                and not any(
                    _domain_matches(excluded, domain, allow_subdomain=True)
                    for excluded in excluded_domains
                )
                and (
                    not required_path_terms
                    or any(term in path for term in required_path_terms)
                )
                for domain, path in zip(top_domains, top_paths)
            )
            if matches >= minimum_domain_matches:
                return "pass", keyword_rule["pass_reason"]
            return "fail", keyword_rule["fail_reason"]

        required_terms = keyword_rule.get("required_terms")
        if required_terms:
            if any(
                all(term in _hit_text(hit) for term in required_terms)
                and (
                    not keyword_rule.get("any_of_terms")
                    or any(
                        cue in _hit_text(hit) for cue in keyword_rule["any_of_terms"]
                    )
                )
                for hit in hits[:3]
            ):
                return "pass", keyword_rule["pass_reason"]
            return "fail", keyword_rule["fail_reason"]

    if case.query_type == "navigational":
        if not expected_domain:
            return "manual", "no expected domain parsed"
        expects_homepage = "homepage should be first" in case.notes.lower()
        allow_subdomain = not expects_homepage
        for idx, (domain, path) in enumerate(zip(top_domains, top_paths), start=1):
            if not _domain_matches(
                expected_domain, domain, allow_subdomain=allow_subdomain
            ):
                continue
            if expects_homepage and path not in {"", "/"}:
                continue
            if idx == 1:
                return "pass", "official destination is rank 1"
            if idx <= 3:
                return "warning", "official destination is rank 2-3"
        return "fail", "official destination missing from top 3"

    if "reference" in case.query_type:
        if not expected_domain:
            return "manual", "no expected domain parsed"
        if any(
            _domain_matches(expected_domain, domain, allow_subdomain=True)
            for domain in top_domains
        ):
            return "pass", "canonical docs are in top 3"
        return "fail", "canonical docs missing from top 3"

    if case.query_type == "news" and expected_domain:
        if any(expected_domain in domain for domain in top_domains):
            return "pass", "expected source is in top 3"
        return "warning", "manual recency review needed"

    if case.query_type in {"overview", "troubleshooting", "comparison", "news"}:
        return "manual", "manual usefulness review required"

    return "manual", "unsupported query type"


def _print_case(case: QueryCase, payload: dict, status: str, reason: str) -> None:
    hits = payload.get("hits") or []
    mode = payload.get("mode", "?")
    total = payload.get("total", 0)
    print(f"[{status.upper()}] {case.query}")
    print(f"  type={case.query_type} tier={case.tier} total={total} mode={mode}")
    print(f"  expected={case.expected}")
    print(f"  notes={case.notes}")
    print(f"  reason={reason}")
    for idx, hit in enumerate(hits[:3], start=1):
        print(f"  {idx}. {hit.get('url', '-')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run search evaluation queries.")
    parser.add_argument(
        "--base-url",
        default="https://palebluesearch.com",
        help="Frontend base URL",
    )
    parser.add_argument(
        "--config",
        default="config/search_eval_cases.json",
        help="Path to the evaluation config JSON file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Result count to fetch for each query",
    )
    parser.add_argument(
        "--tier",
        choices=("all", "1", "2"),
        default="all",
        help="Optional tier filter",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    cases, keyword_rules, known_domains = _load_config(config_path)
    if args.tier != "all":
        cases = [case for case in cases if case.tier == int(args.tier)]

    counts = {"pass": 0, "warning": 0, "fail": 0, "manual": 0}
    errors = 0

    for case in cases:
        try:
            payload = _fetch_results(args.base_url, case.query, args.limit)
            status, reason = _classify_case(
                case,
                payload,
                keyword_rules=keyword_rules,
                known_domains=known_domains,
            )
            counts[status] += 1
            _print_case(case, payload, status, reason)
        except Exception as exc:
            errors += 1
            print(f"[ERROR] {case.query}")
            print(f"  reason={exc}")
        print()

    print("Summary")
    print(
        "  pass={pass} warning={warning} fail={fail} manual={manual} errors={errors}".format(
            errors=errors,
            **counts,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
