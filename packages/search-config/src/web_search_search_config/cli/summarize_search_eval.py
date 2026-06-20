import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from web_search_search_config.canonical_sources import CanonicalEvalCase
from web_search_search_config.search_eval import (
    canonical_search_eval_config,
    load_local_search_eval_config,
    merge_search_eval_configs,
)


def _count_by_query_type(cases: list[CanonicalEvalCase]) -> Counter[str]:
    return Counter(case.query_type for case in cases)


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.000"
    return f"{numerator / denominator:.3f}"


def _print_config_summary(config_path: Path) -> list[CanonicalEvalCase]:
    canonical_config = canonical_search_eval_config()
    local_config = load_local_search_eval_config(config_path)
    merged_config = merge_search_eval_configs(canonical_config, local_config)

    canonical_cases = list(canonical_config.query_cases)
    local_cases = list(local_config.query_cases)
    canonical_keys = {case.query_key for case in canonical_cases}
    local_added = [case for case in local_cases if case.query_key not in canonical_keys]
    local_duplicates = [
        case for case in local_cases if case.query_key in canonical_keys
    ]
    merged_cases = list(merged_config.query_cases)

    print("Evaluation Set")
    print(f"  total_cases={len(merged_cases)}")
    print(f"  canonical_sources={len(canonical_cases)}")
    print(f"  search_eval_cases={len(local_added)}")
    print(f"  ignored_duplicates={len(local_duplicates)}")
    print()

    print("Query Types")
    for query_type, count in sorted(_count_by_query_type(merged_cases).items()):
        print(f"  {query_type}: {count}")
    print()

    return merged_cases


def _load_report(report_path: Path) -> dict[str, Any]:
    return json.loads(report_path.read_text(encoding="utf-8"))


def _print_report_summary(report: dict[str, Any]) -> None:
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise ValueError("report.cases must be a list")

    counts = report.get("counts") or {}
    matched = int(counts.get("matched", 0))
    missed = int(counts.get("missed", 0))
    errors = int(report.get("errors", 0))
    total = matched + missed

    print("Outcomes")
    print(
        f"  total_evaluated={total} matched={matched} missed={missed} "
        f"match_rate={_format_rate(matched, total)} errors={errors}"
    )
    print()

    by_type: dict[str, Counter[str]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        query_type = str(case.get("query_type") or "unknown")
        outcome = str(case.get("outcome") or "unknown")
        by_type.setdefault(query_type, Counter())[outcome] += 1

    print("Outcomes by Query Type")
    for query_type, outcome_counts in sorted(by_type.items()):
        type_matched = int(outcome_counts.get("matched", 0))
        type_missed = int(outcome_counts.get("missed", 0))
        type_total = type_matched + type_missed
        print(
            f"  {query_type}: total={type_total} matched={type_matched} "
            f"missed={type_missed} match_rate={_format_rate(type_matched, type_total)}"
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize search evaluation set distribution and optional outcomes."
    )
    parser.add_argument(
        "--config",
        default="config/search_eval_cases.json",
        help="Path to the local evaluation config JSON file",
    )
    parser.add_argument(
        "--report",
        help="Optional JSON report from web-search-evaluate-search --json-output",
    )
    args = parser.parse_args()

    _print_config_summary(Path(args.config))
    if args.report:
        _print_report_summary(_load_report(Path(args.report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
