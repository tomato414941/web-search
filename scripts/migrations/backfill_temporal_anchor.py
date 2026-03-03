#!/usr/bin/env python3
"""Backfill temporal_anchor scores into OpenSearch.

Computes temporal_anchor from existing published_at field:
  - published_at present -> 1.0
  - published_at absent  -> 0.2

Usage:
    python scripts/migrations/backfill_temporal_anchor.py [--batch-size 1000] [--dry-run]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "src"))

from shared.opensearch.client import get_client, doc_id, INDEX_NAME
from shared.postgres.search import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def compute_temporal_anchor(published_at) -> float:
    if published_at:
        return 1.0
    return 0.2


def backfill(
    batch_size: int = 1000,
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
        cur.execute("SELECT COUNT(*) FROM documents WHERE published_at IS NOT NULL")
        with_date = cur.fetchone()[0]
        logger.info(
            "Dry run: %d with published_at (-> 1.0), %d without (-> 0.2)",
            with_date,
            total - with_date,
        )
        cur.close()
        conn.close()
        return

    client = get_client(opensearch_url)

    offset = 0
    updated = 0
    start = time.time()

    while offset < total:
        cur.execute(
            "SELECT url, published_at FROM documents ORDER BY url LIMIT %s OFFSET %s",
            (batch_size, offset),
        )
        rows = cur.fetchall()
        if not rows:
            break

        # Build bulk update actions
        actions = []
        for url, published_at in rows:
            score = compute_temporal_anchor(published_at)
            actions.append({"update": {"_index": INDEX_NAME, "_id": doc_id(url)}})
            actions.append({"doc": {"temporal_anchor": score}})

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
        description="Backfill temporal_anchor into OpenSearch"
    )
    parser.add_argument("--batch-size", type=int, default=1000)
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
