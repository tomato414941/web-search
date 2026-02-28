#!/usr/bin/env python3
"""Backfill existing PostgreSQL documents into OpenSearch.

Usage:
    python scripts/backfill_opensearch.py [--batch-size 500] [--dry-run]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
import logging
import os
import sys
import time
from urllib.parse import urlparse

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.opensearch.client import bulk_index, get_client
from shared.opensearch.mapping import ensure_index
from shared.db.search import get_connection
from shared.search_kernel.analyzer import analyzer

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


def get_authority_map(conn, urls: list[str]) -> dict[str, float]:
    """Fetch max(page_rank, domain_rank) for a batch of URLs."""
    if not urls:
        return {}

    cur = conn.cursor()
    try:
        # Page ranks
        cur.execute(
            "SELECT url, score FROM page_ranks WHERE url = ANY(%s)",
            (urls,),
        )
        page_ranks = dict(cur.fetchall())

        # Domain ranks
        domains = list({urlparse(u).netloc for u in urls})
        cur.execute(
            "SELECT domain, score FROM domain_ranks WHERE domain = ANY(%s)",
            (domains,),
        )
        domain_ranks = dict(cur.fetchall())

        result = {}
        for url in urls:
            pr = page_ranks.get(url, 0.0)
            dr = domain_ranks.get(urlparse(url).netloc, 0.0)
            result[url] = max(pr, dr)
        return result
    finally:
        cur.close()


def backfill(
    batch_size: int = 500,
    dry_run: bool = False,
    opensearch_url: str = "http://localhost:9200",
) -> None:
    db_path = os.environ.get("DATABASE_URL", "")
    if not db_path:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = get_connection(db_path)
    cur = conn.cursor()

    # Count total documents
    cur.execute("SELECT COUNT(*) FROM documents")
    total = cur.fetchone()[0]
    logger.info("Total documents to backfill: %d", total)

    if dry_run:
        logger.info("Dry run - exiting")
        cur.close()
        conn.close()
        return

    # Init OpenSearch
    client = get_client(opensearch_url)
    ensure_index(client)

    offset = 0
    indexed = 0
    start = time.time()

    while offset < total:
        cur.execute(
            "SELECT url, title, content, word_count, indexed_at "
            "FROM documents ORDER BY url LIMIT %s OFFSET %s",
            (batch_size, offset),
        )
        rows = cur.fetchall()
        if not rows:
            break

        urls = [r[0] for r in rows]
        authority_map = get_authority_map(conn, urls)

        docs = []
        for url, title, content, word_count, indexed_at in rows:
            title_tokens = tokenize_text(title or "")
            content_tokens = tokenize_text(content or "")

            doc = {
                "url": url,
                "title": title_tokens,
                "content": content_tokens,
                "word_count": word_count or 0,
                "indexed_at": indexed_at.isoformat() if indexed_at else None,
                "authority": authority_map.get(url, 0.0),
            }
            docs.append(doc)

        count = bulk_index(client, docs)
        indexed += count
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

    cur.close()
    conn.close()

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
