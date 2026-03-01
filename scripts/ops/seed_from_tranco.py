#!/usr/bin/env python3
"""
Seed crawler with top domains from the Tranco list.

Downloads the Tranco top-1M list and submits the top N domains
as seed URLs to the crawler API.

Usage:
    python scripts/seed_from_tranco.py [--count 1000] [--api-url http://localhost:8082]
"""

import argparse
import csv
import io
import zipfile
from urllib.request import urlopen, Request

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"
DEFAULT_API_URL = "http://localhost:8082"
DEFAULT_COUNT = 1000
BATCH_SIZE = 100


def download_tranco(count: int) -> list[str]:
    """Download Tranco list and return top N domains."""
    print(f"Downloading Tranco list from {TRANCO_URL}...")
    req = Request(TRANCO_URL, headers={"User-Agent": "PaleblueBot/1.0"})
    with urlopen(req, timeout=30) as resp:
        zip_data = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            domains = []
            for row in reader:
                if len(row) >= 2:
                    domains.append(row[1].strip())
                if len(domains) >= count:
                    break

    print(f"Got {len(domains)} domains from Tranco list")
    return domains


def submit_seeds(api_url: str, domains: list[str]) -> int:
    """Submit domains as seed URLs to crawler API."""
    import json

    total_added = 0

    for i in range(0, len(domains), BATCH_SIZE):
        batch = domains[i : i + BATCH_SIZE]
        urls = [f"https://{d}/" for d in batch]

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
                print(f"  Batch {i // BATCH_SIZE + 1}: {added} seeds added")
        except Exception as e:
            print(f"  Batch {i // BATCH_SIZE + 1}: ERROR - {e}")

    return total_added


def main():
    parser = argparse.ArgumentParser(description="Seed crawler from Tranco list")
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT, help="Number of top domains"
    )
    parser.add_argument(
        "--api-url", default=DEFAULT_API_URL, help="Crawler API base URL"
    )
    args = parser.parse_args()

    domains = download_tranco(args.count)
    total = submit_seeds(args.api_url, domains)
    print(f"\nDone: {total} seeds added from top {args.count} Tranco domains")


if __name__ == "__main__":
    main()
