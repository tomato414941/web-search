#!/usr/bin/env python3
"""Rebuild the OpenSearch search projection from PostgreSQL source data.

Usage:
    web-search-rebuild-search-projection [--batch-size 500] [--dry-run]
        [--start-after-url URL] [--max-documents N]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
from dataclasses import dataclass
import logging
import os
import sys
import time

from web_search_opensearch.client import bulk_index, get_client
from web_search_opensearch.mapping import ensure_index
from web_search_indexer.services.opensearch_document import build_search_index_document
from web_search_postgres.repositories import DocumentRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProjectionPage:
    url: str
    title: str
    content: str


def rebuild_search_projection(
    batch_size: int = 500,
    dry_run: bool = False,
    opensearch_url: str = "http://localhost:9200",
    start_after_url: str | None = None,
    max_documents: int | None = None,
) -> None:
    if not os.environ.get("DATABASE_URL", ""):
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    total = DocumentRepository.count_documents()
    logger.info("Total documents to project: %d", total)

    if dry_run:
        logger.info("Dry run - exiting")
        return

    client = get_client(opensearch_url)
    ensure_index(client)

    indexed = 0
    scanned = 0
    last_url = start_after_url
    target = max_documents if max_documents is not None else total
    start = time.time()

    while scanned < target:
        limit = min(batch_size, target - scanned)
        rows = DocumentRepository.fetch_documents_for_opensearch_after_url(
            limit=limit,
            last_url=last_url,
        )
        if not rows:
            break
        last_url = rows[-1][0]

        urls = [url for url, *_ in rows]
        link_rank_map = DocumentRepository.fetch_link_rank_map(urls)

        docs = []
        for (
            url,
            title,
            content,
        ) in rows:
            page_rank, domain_rank = link_rank_map.get(url, (0.0, 0.0))
            doc = build_search_index_document(
                ProjectionPage(
                    url=url,
                    title=title,
                    content=content,
                ),
                page_rank=page_rank,
                domain_rank=domain_rank,
            )
            if doc is not None:
                docs.append(doc)

        indexed += bulk_index(client, docs)
        scanned += len(rows)

        elapsed = time.time() - start
        rate = indexed / elapsed if elapsed > 0 else 0
        logger.info(
            "Progress: %d/%d scanned, %d indexed (%.1f%%) - %.0f indexed docs/sec; last_url=%s",
            scanned,
            target,
            indexed,
            scanned / target * 100 if target > 0 else 100,
            rate,
            last_url,
        )

    elapsed = time.time() - start
    logger.info(
        "Search projection rebuild complete: %d/%d documents in %.1fs (%.0f docs/sec); last_url=%s",
        indexed,
        target,
        elapsed,
        indexed / elapsed if elapsed > 0 else 0,
        last_url,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild the OpenSearch search projection from PostgreSQL"
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-after-url")
    parser.add_argument("--max-documents", type=int)
    parser.add_argument(
        "--opensearch-url",
        default=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
    )
    args = parser.parse_args()

    rebuild_search_projection(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        opensearch_url=args.opensearch_url,
        start_after_url=args.start_after_url,
        max_documents=args.max_documents,
    )


if __name__ == "__main__":
    main()
