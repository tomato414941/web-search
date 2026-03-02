#!/usr/bin/env python3
"""
Seed crawler with curated AI-focused domains.

Reads crawler/data/ai_seeds.csv and submits domains as seed URLs
to the crawler API, grouped by category.

Usage:
    python scripts/ops/seed_from_ai_list.py [--api-url http://localhost:8082]
    python scripts/ops/seed_from_ai_list.py --dry-run
    python scripts/ops/seed_from_ai_list.py --category docs
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.request import urlopen, Request

DEFAULT_API_URL = "http://localhost:8082"
SEED_FILE = (
    Path(__file__).resolve().parent.parent.parent / "crawler" / "data" / "ai_seeds.csv"
)
BATCH_SIZE = 50


def load_seeds(path: Path, category: str | None = None) -> dict[str, list[str]]:
    """Load seeds from CSV, grouped by category.

    Returns:
        dict mapping category -> list of domains
    """
    groups: dict[str, list[str]] = {}

    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
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

            groups.setdefault(cat, []).append(domain)

    return groups


def submit_seeds(api_url: str, domains: list[str]) -> int:
    """Submit domains as seed URLs to crawler API."""
    total_added = 0

    for i in range(0, len(domains), BATCH_SIZE):
        batch = domains[i : i + BATCH_SIZE]
        urls = []
        for d in batch:
            if d.startswith("http"):
                urls.append(d if d.endswith("/") else d + "/")
            else:
                urls.append(f"https://{d}/")

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
                added = result.get("count", 0)
                total_added += added
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    return total_added


def main():
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
        sys.exit(1)

    groups = load_seeds(args.seed_file, args.category)

    if not groups:
        print("No seeds found.", file=sys.stderr)
        sys.exit(1)

    grand_total = 0
    for cat, domains in groups.items():
        if args.dry_run:
            print(f"\n[{cat}] {len(domains)} domains:")
            for d in domains:
                print(f"  https://{d}/")
            grand_total += len(domains)
        else:
            added = submit_seeds(args.api_url, domains)
            print(f"  [{cat}] {added}/{len(domains)} seeds added")
            grand_total += added

    if args.dry_run:
        print(f"\nDry run: {grand_total} domains total (not submitted)")
    else:
        print(f"\nDone: {grand_total} seeds added")


if __name__ == "__main__":
    main()
