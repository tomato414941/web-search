#!/usr/bin/env python3
"""Rebuild the OpenSearch search projection from PostgreSQL source data.

Usage:
    web-search-rebuild-search-projection [--batch-size 100] [--dry-run]
        [--start-after-url URL | --checkpoint-file PATH] [--max-documents N]

Requires:
    DATABASE_URL, OPENSEARCH_URL, and OPENROUTER_API_KEY environment variables.
"""

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

from web_search_opensearch.client import (
    bulk_index,
    get_client,
    index_name as resolve_index,
)
from web_search_opensearch.mapping import SCHEMA, ensure_index
from web_search_indexer.cli.projection_checkpoint import (
    ProjectionCheckpoint,
    ProjectionProgress,
)
from web_search_indexer.services.opensearch_document import (
    SEARCH_CONTENT_MAX_CHARS,
    build_search_index_documents,
)
from web_search_postgres.repositories import DocumentRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100


@dataclass(slots=True)
class ProjectionPage:
    url: str
    title: str
    content: str


def rebuild_search_projection(
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    opensearch_url: str = "http://localhost:9200",
    index_name: str | None = None,
    start_after_url: str | None = None,
    max_documents: int | None = None,
    checkpoint_file: Path | None = None,
) -> None:
    if batch_size < 1 or (max_documents is not None and max_documents < 1):
        raise ValueError("Batch size and maximum document count must be positive")
    if checkpoint_file is not None and start_after_url is not None:
        raise ValueError("Use either a checkpoint file or --start-after-url")
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    total = (
        max_documents
        if max_documents is not None
        else DocumentRepository.count_documents()
    )
    logger.info("Total documents to project: %d", total)

    if dry_run:
        logger.info("Dry run - exiting")
        return

    checkpoint = (
        ProjectionCheckpoint(Path(checkpoint_file))
        if checkpoint_file is not None
        else None
    )
    with checkpoint or nullcontext():
        client = get_client(opensearch_url)
        ensure_index(client, target_index=index_name)
        identity = {}
        progress = ProjectionProgress(last_url=start_after_url)
        if checkpoint is not None:
            settings = client.indices.get_settings(index=resolve_index(index_name))
            if len(settings) != 1:
                raise ValueError("Rebuild must target exactly one physical index")
            physical_index, settings = next(iter(settings.items()))
            source = urlsplit(database_url)
            identity = {
                "source": {
                    "host": source.hostname,
                    "port": source.port or 5432,
                    "database": source.path,
                },
                "index": physical_index,
                "index_uuid": settings["settings"]["index"]["uuid"],
                "schema": SCHEMA,
                "content_max_chars": SEARCH_CONTENT_MAX_CHARS,
            }
            progress = checkpoint.load(identity)
            if progress.complete:
                logger.info("Search projection rebuild is already complete")
                return
            checkpoint.save(identity, progress)

        scanned = 0
        indexed = 0
        start = time.monotonic()
        while max_documents is None or scanned < max_documents:
            limit = (
                batch_size
                if max_documents is None
                else min(batch_size, max_documents - scanned)
            )
            rows = DocumentRepository.fetch_documents_for_opensearch_after_url(
                limit=limit,
                last_url=progress.last_url,
            )
            if not rows:
                progress.complete = True
                if checkpoint is not None:
                    checkpoint.save(identity, progress)
                break

            docs = build_search_index_documents(
                [ProjectionPage(url, title, content) for url, title, content in rows]
            )
            count = bulk_index(client, docs, target_index=index_name)
            if count != len(docs):
                raise RuntimeError(
                    f"Hybrid projection failed: {count}/{len(docs)} documents indexed"
                )
            indexed += count
            scanned += len(rows)
            progress.indexed += count
            progress.scanned += len(rows)
            progress.last_url = rows[-1][0]
            if checkpoint is not None:
                checkpoint.save(identity, progress)

            elapsed = time.monotonic() - start
            rate = indexed / elapsed if elapsed > 0 else 0
            logger.info(
                "Progress: %d scanned, %d indexed (%.0f indexed docs/sec); last_url=%s",
                progress.scanned,
                progress.indexed,
                rate,
                progress.last_url,
            )

        elapsed = time.monotonic() - start
        logger.info(
            "Search projection %s: %d scanned, %d indexed in %.1fs; last_url=%s",
            "rebuild complete" if progress.complete else "segment complete",
            scanned,
            indexed,
            elapsed,
            progress.last_url,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild the OpenSearch search projection from PostgreSQL"
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument("--start-after-url")
    resume.add_argument(
        "--checkpoint-file",
        type=Path,
        help="Save acknowledged batch progress and resume this rebuild on restart.",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        help="Maximum source rows to scan in this invocation.",
    )
    parser.add_argument(
        "--opensearch-url",
        default=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
    )
    parser.add_argument(
        "--index-name",
        default=os.environ.get("OPENSEARCH_INDEX_NAME"),
        help=(
            "OpenSearch hybrid index to rebuild. Defaults to "
            "OPENSEARCH_INDEX_NAME or documents-hybrid-v2."
        ),
    )
    args = parser.parse_args()

    rebuild_search_projection(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        opensearch_url=args.opensearch_url,
        index_name=args.index_name,
        start_after_url=args.start_after_url,
        max_documents=args.max_documents,
        checkpoint_file=args.checkpoint_file,
    )


if __name__ == "__main__":
    main()
