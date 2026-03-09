#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SEEDS = (
    "google",
    "github",
    "fastapi",
    "openai",
    "python",
    "postgresql",
    "docker",
    "pytest",
    "django",
    "opensearch",
    "elasticsearch",
    "site reliability engineering",
    "bm25",
)


@dataclass
class QueryCandidate:
    query: str
    sources: set[str] = field(default_factory=set)
    seeds: set[str] = field(default_factory=set)
    count: int | None = None


def _normalize_query(query: str) -> str:
    return " ".join((query or "").strip().split())


def _load_dotenv_if_present() -> None:
    for env_path in (Path(".env"), Path(".env.local")):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _fetch_duckduckgo_suggestions(seed: str, limit: int) -> list[str]:
    url = "https://duckduckgo.com/ac/?" + urllib.parse.urlencode(
        {"q": seed, "type": "list"}
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pbs-query-collector/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    suggestions: list[str] = []
    if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
        suggestions = [str(item) for item in payload[1]]
    return suggestions[:limit]


def _fetch_internal_queries(days: int, limit: int) -> list[tuple[str, int, str]]:
    _load_dotenv_if_present()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return []

    try:
        import psycopg2
    except ImportError:
        return []

    queries: list[tuple[str, int, str]] = []
    sql = """
        WITH recent AS (
            SELECT query, result_count
            FROM search_logs
            WHERE created_at >= NOW() - (%s || ' days')::interval
        )
        (
            SELECT query, COUNT(*)::int AS count, 'internal-top' AS source
            FROM recent
            GROUP BY query
            ORDER BY count DESC, query ASC
            LIMIT %s
        )
        UNION ALL
        (
            SELECT query, COUNT(*)::int AS count, 'internal-zero-hit' AS source
            FROM recent
            WHERE result_count = 0
            GROUP BY query
            ORDER BY count DESC, query ASC
            LIMIT %s
        )
    """
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(days), limit, limit))
            rows = cur.fetchall()
    for query, count, source in rows:
        if not query:
            continue
        queries.append((str(query), int(count), str(source)))
    return queries


def _collect_candidates(
    *,
    seeds: tuple[str, ...],
    ddg_limit: int,
    internal_days: int,
    internal_limit: int,
) -> list[QueryCandidate]:
    candidates: dict[str, QueryCandidate] = {}

    for seed in seeds:
        normalized_seed = _normalize_query(seed)
        if not normalized_seed:
            continue
        for query in _fetch_duckduckgo_suggestions(seed, ddg_limit):
            normalized = _normalize_query(query)
            if not normalized:
                continue
            candidate = candidates.setdefault(
                normalized, QueryCandidate(query=normalized)
            )
            candidate.sources.add("duckduckgo")
            candidate.seeds.add(normalized_seed)

    for query, count, source in _fetch_internal_queries(internal_days, internal_limit):
        normalized = _normalize_query(query)
        if not normalized:
            continue
        candidate = candidates.setdefault(normalized, QueryCandidate(query=normalized))
        candidate.sources.add(source)
        candidate.count = max(candidate.count or 0, count)

    return sorted(
        candidates.values(),
        key=lambda item: (
            -(item.count or 0),
            -len(item.sources),
            item.query.lower(),
        ),
    )


def _render_markdown(candidates: list[QueryCandidate], limit: int) -> str:
    lines = [
        "| Query | Sources | Seeds | Count |",
        "|---|---|---|---|",
    ]
    for item in candidates[:limit]:
        sources = ", ".join(sorted(item.sources))
        seeds = ", ".join(sorted(item.seeds))
        count = str(item.count) if item.count is not None else ""
        lines.append(f"| `{item.query}` | {sources} | {seeds} | {count} |")
    return "\n".join(lines) + "\n"


def _render_json(candidates: list[QueryCandidate], limit: int) -> str:
    payload = [
        {
            "query": item.query,
            "sources": sorted(item.sources),
            "seeds": sorted(item.seeds),
            "count": item.count,
        }
        for item in candidates[:limit]
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect proactive search query candidates from DuckDuckGo autocomplete "
            "and optional internal search logs."
        )
    )
    parser.add_argument(
        "--seed",
        action="append",
        dest="seeds",
        default=[],
        help="Seed topic to expand. Repeatable. Defaults to the built-in seed set.",
    )
    parser.add_argument(
        "--ddg-limit",
        type=int,
        default=8,
        help="Max DuckDuckGo suggestions per seed (default: 8).",
    )
    parser.add_argument(
        "--internal-days",
        type=int,
        default=30,
        help="Lookback window for internal search_logs in days (default: 30).",
    )
    parser.add_argument(
        "--internal-limit",
        type=int,
        default=25,
        help="Max internal top / zero-hit queries to fetch per bucket (default: 25).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max rows to print (default: 50).",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown).",
    )
    args = parser.parse_args()

    seeds = tuple(args.seeds) if args.seeds else DEFAULT_SEEDS
    candidates = _collect_candidates(
        seeds=seeds,
        ddg_limit=args.ddg_limit,
        internal_days=args.internal_days,
        internal_limit=args.internal_limit,
    )

    if args.format == "json":
        sys.stdout.write(_render_json(candidates, args.limit))
    else:
        sys.stdout.write(_render_markdown(candidates, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
