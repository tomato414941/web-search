#!/usr/bin/env python3
"""Backfill factual_density scores into OpenSearch.

Reads content from PostgreSQL documents table, computes factual_density,
and updates the corresponding OpenSearch documents.

Usage:
    python scripts/migrations/backfill_factual_density.py [--batch-size 200] [--dry-run]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "src"))

from shared.opensearch.client import doc_id, get_client, INDEX_NAME
from shared.postgres.search import get_connection
from shared.search_kernel.factual_density import compute_factual_density

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
    db_path = os.environ.get("DATABASE_URL", "")
    if not db_path:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM documents")
    total = cur.fetchone()[0]
    logger.info("Total documents: %d", total)

    if dry_run:
        logger.info("Dry run — would compute factual_density for %d docs", total)
        cur.close()
        conn.close()
        return

    client = get_client(opensearch_url)

    offset = 0
    updated = 0
    start = time.time()

    while offset < total:
        cur.execute(
            "SELECT url, content, word_count "
            "FROM documents ORDER BY url LIMIT %s OFFSET %s",
            (batch_size, offset),
        )
        rows = cur.fetchall()
        if not rows:
            break

        actions = []
        for url, content, word_count in rows:
            score = compute_factual_density(
                content or "",
                word_count=word_count or 0,
            )
            actions.append({"update": {"_index": INDEX_NAME, "_id": doc_id(url)}})
            actions.append({"doc": {"factual_density": score}})

        try:
            resp = client.bulk(body=actions)
            errors = sum(
                1
                for item in resp.get("items", [])
                if item.get("update", {}).get("error")
            )
            updated += len(rows) - errors
        except Exception as e:
            logger.warning("Bulk update failed at offset %d: %s", offset, e)

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

    cur.close()
    conn.close()

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
