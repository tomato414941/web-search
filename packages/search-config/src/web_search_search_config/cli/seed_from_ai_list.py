import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from web_search_search_config.canonical_sources import canonical_seed_rows

DEFAULT_API_URL = "http://localhost:8082"
SEED_FILE = Path("apps/crawler/data/ai_seeds.csv")
BATCH_SIZE = 50


def load_seeds(
    path: Path,
    category: str | None = None,
    *,
    include_canonical: bool = True,
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    with open(path, encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            line = row[0].strip() if row else ""
            if not line or line.startswith("#") or line.startswith("="):
                continue
            if len(row) < 2:
                continue

            cat = row[0].strip()
            domain = row[1].strip()

            if category and cat != category:
                continue

            groups.setdefault(cat, [])
            seen.setdefault(cat, set())
            if domain in seen[cat]:
                continue
            groups[cat].append(domain)
            seen[cat].add(domain)

    if include_canonical:
        for seed_row in canonical_seed_rows(category):
            groups.setdefault(seed_row.category, [])
            seen.setdefault(seed_row.category, set())
            if seed_row.target in seen[seed_row.category]:
                continue
            groups[seed_row.category].append(seed_row.target)
            seen[seed_row.category].add(seed_row.target)

    return groups


def submit_seeds(api_url: str, domains: list[str]) -> int:
    total_added = 0

    for start in range(0, len(domains), BATCH_SIZE):
        batch = domains[start : start + BATCH_SIZE]
        urls = [_normalize_seed_url(seed) for seed in batch]

        payload = json.dumps({"urls": urls}).encode()
        req = Request(
            f"{api_url}/api/v1/seeds",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                total_added += result.get("count", 0)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)

    return total_added


def _normalize_seed_url(seed: str) -> str:
    if seed.startswith(("http://", "https://")):
        parsed = urlparse(seed)
        if not parsed.path and not parsed.query and not parsed.fragment:
            return seed.rstrip("/") + "/"
        return seed

    return f"https://{seed.rstrip('/')}/"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed crawler from AI-focused domain list"
    )
    parser.add_argument(
        "--api-url", default=DEFAULT_API_URL, help="Crawler API base URL"
    )
    parser.add_argument(
        "--seed-file", type=Path, default=SEED_FILE, help="Path to ai_seeds.csv"
    )
    parser.add_argument(
        "--category", help="Only seed a specific category (e.g. docs, japanese)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print domains without submitting"
    )
    args = parser.parse_args()

    if not args.seed_file.exists():
        print(f"Seed file not found: {args.seed_file}", file=sys.stderr)
        return 1

    groups = load_seeds(args.seed_file, args.category)
    if not groups:
        print("No seeds found.", file=sys.stderr)
        return 1

    grand_total = 0
    for cat, domains in groups.items():
        if args.dry_run:
            print(f"\n[{cat}] {len(domains)} domains:")
            for domain in domains:
                print(f"  {_normalize_seed_url(domain)}")
            grand_total += len(domains)
            continue

        added = submit_seeds(args.api_url, domains)
        print(f"  [{cat}] {added}/{len(domains)} seeds added")
        grand_total += added

    if args.dry_run:
        print(f"\nDry run: {grand_total} domains total (not submitted)")
    else:
        print(f"\nDone: {grand_total} seeds added")
    return 0
