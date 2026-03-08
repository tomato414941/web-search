#!/usr/bin/env python3

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


QUERY_SET_HEADER = "## Minimum Golden Query Set"
PASS_CRITERIA_HEADER = "## Pass Criteria"


@dataclass
class QueryCase:
    query: str
    query_type: str
    expected: str
    notes: str


def _parse_query_cases(doc_path: Path) -> list[QueryCase]:
    text = doc_path.read_text(encoding="utf-8")
    start = text.index(QUERY_SET_HEADER)
    end = text.index(PASS_CRITERIA_HEADER, start)
    section = text[start:end]

    cases: list[QueryCase] = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        query, query_type, expected, notes = cells
        cases.append(
            QueryCase(
                query=query.strip("`"),
                query_type=query_type,
                expected=expected.strip("`"),
                notes=notes,
            )
        )
    if not cases:
        raise ValueError(f"No query cases found in {doc_path}")
    return cases


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


def _extract_domain(text: str) -> str | None:
    match = re.search(r"`([^`]+)`", text)
    if match:
        return match.group(1).lower()

    known_domains = [
        "google.com",
        "github.com",
        "fastapi.tiangolo.com",
        "platform.openai.com",
        "docs.python.org",
        "postgresql.org",
    ]
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


def _domain_matches(
    expected_domain: str, actual_domain: str, *, allow_subdomain: bool
) -> bool:
    if actual_domain == expected_domain or actual_domain == f"www.{expected_domain}":
        return True
    if allow_subdomain and actual_domain.endswith(f".{expected_domain}"):
        return True
    return False


def _classify_case(case: QueryCase, payload: dict) -> tuple[str, str]:
    hits = payload.get("hits") or []
    total = int(payload.get("total") or 0)
    expected_domain = _extract_domain(case.expected)
    top_urls = [hit.get("url", "") for hit in hits[:3]]
    top_domains = [_normalize_url_domain(url) for url in top_urls]
    top_paths = [_normalize_url_path(url) for url in top_urls]

    if total == 0:
        return "fail", "0 hits"

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
    print(f"  type={case.query_type} total={total} mode={mode}")
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
        "--doc",
        default="docs/search-evaluation.md",
        help="Path to the query set document",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Result count to fetch for each query",
    )
    args = parser.parse_args()

    doc_path = Path(args.doc)
    cases = _parse_query_cases(doc_path)

    counts = {"pass": 0, "warning": 0, "fail": 0, "manual": 0}
    errors = 0

    for case in cases:
        try:
            payload = _fetch_results(args.base_url, case.query, args.limit)
            status, reason = _classify_case(case, payload)
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
