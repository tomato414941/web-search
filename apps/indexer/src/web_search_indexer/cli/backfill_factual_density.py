#!/usr/bin/env python3
"""Backfill factual_density scores into OpenSearch.

Reads content from PostgreSQL documents table, computes factual_density,
and updates the corresponding OpenSearch documents.

Usage:
    web-search-backfill-factual-density [--batch-size 200] [--dry-run]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
import logging
import os
import sys
import time

from web_search_kernel.factual_density import compute_factual_density
from web_search_opensearch.client import INDEX_NAME, doc_id, get_client
from web_search_postgres.repositories import DocumentRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def backfill(
    batch_size: int = 200,
    dry_run: bool = False,
    opensearch_url: str = "http://localhost:9200",
) -> None:
    if not os.environ.get("DATABASE_URL", ""):
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    total = DocumentRepository.count_documents()
    logger.info("Total documents: %d", total)

    if dry_run:
        logger.info("Dry run - would compute factual_density for %d docs", total)
        return

    client = get_client(opensearch_url)
    offset = 0
    updated = 0
    start = time.time()

    while offset < total:
        rows = DocumentRepository.fetch_documents_for_factual_density(
            limit=batch_size,
            offset=offset,
        )
        if not rows:
            break

        actions = []
        for url, content, word_count in rows:
            score = compute_factual_density(content, word_count=word_count)
            actions.append({"update": {"_index": INDEX_NAME, "_id": doc_id(url)}})
            actions.append({"doc": {"factual_density": score}})

        try:
            response = client.bulk(body=actions)
            errors = sum(
                1
                for item in response.get("items", [])
                if item.get("update", {}).get("error")
            )
            updated += len(rows) - errors
        except Exception as exc:
            logger.warning("Bulk update failed at offset %d: %s", offset, exc)

        offset += len(rows)
        elapsed = time.time() - start
        rate = updated / elapsed if elapsed > 0 else 0
        logger.info(
            "Progress: %d/%d (%.1f%%) - %.0f docs/sec",
            updated,
            total,
            updated / total * 100,
            rate,
        )

    elapsed = time.time() - start
    logger.info(
        "Backfill complete: %d/%d documents in %.1fs (%.0f docs/sec)",
        updated,
        total,
        elapsed,
        updated / elapsed if elapsed > 0 else 0,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Backfill factual_density into OpenSearch"
    )
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--opensearch-url",
        default=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
    )
    args = parser.parse_args()

    backfill(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        opensearch_url=args.opensearch_url,
    )


if __name__ == "__main__":
    main()
