#!/usr/bin/env python3
"""Backfill existing PostgreSQL documents into OpenSearch.

Usage:
    web-search-backfill-opensearch [--batch-size 500] [--dry-run]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
import logging
import os
import sys
import time

from web_search_kernel.analyzer import analyzer
from web_search_opensearch.client import bulk_index, get_client
from web_search_opensearch.mapping import ensure_index
from web_search_postgres.repositories import DocumentRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def tokenize_text(text: str) -> str:
    """Tokenize text using SudachiPy analyzer."""
    if not text:
        return ""
    return analyzer.tokenize(text)


def backfill(
    batch_size: int = 500,
    dry_run: bool = False,
    opensearch_url: str = "http://localhost:9200",
) -> None:
    if not os.environ.get("DATABASE_URL", ""):
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    total = DocumentRepository.count_documents()
    logger.info("Total documents to backfill: %d", total)

    if dry_run:
        logger.info("Dry run - exiting")
        return

    client = get_client(opensearch_url)
    ensure_index(client)

    try:
        opensearch_count = client.count(index="documents")["count"]
        logger.info("OpenSearch currently has %d documents", opensearch_count)
        if opensearch_count >= total and total > 0:
            logger.info(
                "OpenSearch already up to date (%d >= %d), skipping",
                opensearch_count,
                total,
            )
            return
    except Exception:
        logger.info("Could not check OpenSearch count, proceeding with backfill")

    indexed = 0
    offset = 0
    start = time.time()

    while offset < total:
        rows = DocumentRepository.fetch_documents_for_opensearch(
            limit=batch_size,
            offset=offset,
        )
        if not rows:
            break

        urls = [url for url, *_ in rows]
        link_rank_map = DocumentRepository.fetch_link_rank_map(urls)

        docs = []
        for url, title, content, word_count, indexed_at in rows:
            page_rank, domain_rank = link_rank_map.get(url, (0.0, 0.0))
            docs.append(
                {
                    "url": url,
                    "title": tokenize_text(title),
                    "content": tokenize_text(content),
                    "word_count": word_count,
                    "indexed_at": indexed_at.isoformat() if indexed_at else None,
                    "page_rank": page_rank,
                    "domain_rank": domain_rank,
                }
            )

        indexed += bulk_index(client, docs)
        offset += len(rows)

        elapsed = time.time() - start
        rate = indexed / elapsed if elapsed > 0 else 0
        logger.info(
            "Progress: %d/%d (%.1f%%) - %.0f docs/sec",
            indexed,
            total,
            indexed / total * 100,
            rate,
        )

    elapsed = time.time() - start
    logger.info(
        "Backfill complete: %d/%d documents in %.1fs (%.0f docs/sec)",
        indexed,
        total,
        elapsed,
        indexed / elapsed if elapsed > 0 else 0,
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill OpenSearch from PostgreSQL")
    parser.add_argument("--batch-size", type=int, default=500)
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
