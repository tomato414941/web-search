import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

from web_search_search_config.canonical_sources import CanonicalEvalCase
from web_search_search_config.evaluator import (
    CaseEvaluation,
    build_report,
    classify_case,
    compute_case_metrics,
    extract_domain,
)
from web_search_search_config.search_eval import load_merged_search_eval_config


def _load_config(
    config_path: Path,
) -> tuple[list[CanonicalEvalCase], dict[str, dict], list[str]]:
    merged = load_merged_search_eval_config(config_path)
    cases = list(merged.query_cases)
    if not cases:
        raise ValueError(f"No query cases found in {config_path}")
    return cases, merged.keyword_rules, list(merged.known_domains)


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
    return extract_domain(text, known_domains)


def _classify_case(
    case: CanonicalEvalCase,
    payload: dict,
    *,
    keyword_rules: dict[str, dict],
    known_domains: list[str],
) -> tuple[str, str]:
    return classify_case(
        case,
        payload,
        keyword_rules=keyword_rules,
        known_domains=known_domains,
    )


def _print_case(
    case: CanonicalEvalCase,
    payload: dict,
    status: str,
    reason: str,
    *,
    metrics: dict[str, float | int | None],
    relevances: list[int],
) -> None:
    hits = payload.get("hits") or []
    mode = payload.get("mode", "?")
    total = payload.get("total", 0)
    print(f"[{status.upper()}] {case.query}")
    print(f"  type={case.query_type} tier={case.tier} total={total} mode={mode}")
    print(f"  expected={case.expected}")
    print(f"  notes={case.notes}")
    print(f"  reason={reason}")
    print(
        "  metrics="
        f"hit@1={metrics['hit_at_1']:.2f} "
        f"hit@3={metrics['hit_at_3']:.2f} "
        f"mrr={metrics['mrr']:.3f} "
        f"ndcg@3={metrics['ndcg_at_3']:.3f}"
    )
    for idx, hit in enumerate(hits[:3], start=1):
        print(f"  {idx}. [{relevances[idx - 1]}] {hit.get('url', '-')}")


def _has_blocking_failures(cases: list[CaseEvaluation]) -> bool:
    return any(case.tier == 1 and case.status == "fail" for case in cases)


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
    parser.add_argument(
        "--json-output",
        help="Optional path to write a machine-readable JSON report",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    cases, keyword_rules, known_domains = _load_config(config_path)
    if args.tier != "all":
        cases = [case for case in cases if case.tier == int(args.tier)]

    counts = {"pass": 0, "warning": 0, "fail": 0, "manual": 0}
    errors = 0
    evaluated_cases: list[CaseEvaluation] = []

    for case in cases:
        try:
            payload = _fetch_results(args.base_url, case.query, args.limit)
            status, reason = _classify_case(
                case,
                payload,
                keyword_rules=keyword_rules,
                known_domains=known_domains,
            )
            metrics, relevances = compute_case_metrics(
                case,
                payload,
                keyword_rules=keyword_rules,
                known_domains=known_domains,
            )
            counts[status] += 1
            _print_case(
                case,
                payload,
                status,
                reason,
                metrics=metrics,
                relevances=relevances,
            )
            evaluated_cases.append(
                CaseEvaluation(
                    query=case.query,
                    query_type=case.query_type,
                    tier=case.tier,
                    status=status,
                    reason=reason,
                    metrics=metrics,
                    total=int(payload.get("total") or 0),
                    mode=str(payload.get("mode", "?")),
                    expected=case.expected,
                    notes=case.notes,
                    top_hits=[
                        {
                            "rank": index,
                            "relevance": relevances[index - 1],
                            "url": hit.get("url"),
                            "title": hit.get("title"),
                        }
                        for index, hit in enumerate(payload.get("hits")[:3], start=1)
                    ],
                )
            )
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
    report = build_report(
        base_url=args.base_url,
        limit=args.limit,
        counts=counts,
        cases=evaluated_cases,
        errors=errors,
    )
    blocking_failures = _has_blocking_failures(evaluated_cases)
    if blocking_failures:
        print("Gate")
        print("  blocking tier-1 failures detected")
    print("Metrics")
    for group, metrics in report.aggregate_metrics.items():
        if not metrics:
            continue
        print(
            "  {group}: hit@1={hit_at_1:.3f} hit@3={hit_at_3:.3f} "
            "mrr={mrr:.3f} ndcg@3={ndcg_at_3:.3f} ndcg@10={ndcg_at_10:.3f}".format(
                group=group,
                **metrics,
            )
        )
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return 1 if errors or blocking_failures else 0
