#!/usr/bin/env python3
"""Backfill embeddings for existing documents into page_embeddings (pgvector).

Usage:
    python scripts/migrations/backfill_embeddings.py [--batch-size 50] [--dry-run]

Requires:
    DATABASE_URL and OPENAI_API_KEY environment variables.
"""

import argparse
import logging
import os
import sys
import time

import numpy as np
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.embedding import MAX_CHARS, _prepare_text, serialize, to_pgvector
from shared.postgres.search import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
# OpenAI allows up to 2048 inputs per request but we keep it modest
API_BATCH_SIZE = 100


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API with retry."""
    prepared = [_prepare_text(t) for t in texts]
    response = client.embeddings.create(input=prepared, model=MODEL)
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [d.embedding for d in sorted_data]


def backfill(
    batch_size: int = 50,
    dry_run: bool = False,
) -> None:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = get_connection(db_url)
    cur = conn.cursor()

    # Count documents without embeddings
    cur.execute(
        "SELECT COUNT(*) FROM documents d "
        "LEFT JOIN page_embeddings pe ON d.url = pe.url "
        "WHERE pe.url IS NULL"
    )
    pending = cur.fetchone()[0]
    logger.info("Documents without embeddings: %d", pending)

    if pending == 0:
        logger.info("All documents already have embeddings, skipping")
        cur.close()
        conn.close()
        return

    if dry_run:
        logger.info("Dry run - exiting")
        cur.close()
        conn.close()
        return

    client = OpenAI(api_key=api_key)
    embedded = 0
    start = time.time()

    while True:
        # Fetch batch of documents without embeddings
        cur.execute(
            "SELECT d.url, d.content FROM documents d "
            "LEFT JOIN page_embeddings pe ON d.url = pe.url "
            "WHERE pe.url IS NULL "
            "ORDER BY d.url LIMIT %s",
            (batch_size,),
        )
        rows = cur.fetchall()
        if not rows:
            break

        urls = [r[0] for r in rows]
        contents = [r[1] or "" for r in rows]

        # Embed in API_BATCH_SIZE chunks
        for i in range(0, len(contents), API_BATCH_SIZE):
            chunk_urls = urls[i : i + API_BATCH_SIZE]
            chunk_contents = contents[i : i + API_BATCH_SIZE]

            try:
                vectors = _embed_batch(client, chunk_contents)
            except Exception as e:
                logger.error("Embedding failed, stopping: %s", e)
                conn.commit()
                cur.close()
                conn.close()
                sys.exit(1)

            # Upsert into page_embeddings
            insert_cur = conn.cursor()
            for url, vec_list in zip(chunk_urls, vectors):
                vec = np.array(vec_list, dtype=np.float32)
                pg_value = to_pgvector(vec)
                insert_cur.execute(
                    "INSERT INTO page_embeddings (url, embedding) VALUES (%s, %s) "
                    "ON CONFLICT (url) DO UPDATE SET embedding = EXCLUDED.embedding",
                    (url, pg_value),
                )
            insert_cur.close()
            conn.commit()

            embedded += len(chunk_urls)

        elapsed = time.time() - start
        rate = embedded / elapsed if elapsed > 0 else 0
        logger.info(
            "Progress: %d/%d (%.1f%%) - %.1f docs/sec",
            embedded,
            pending,
            embedded / pending * 100,
            rate,
        )

    cur.close()
    conn.close()

    elapsed = time.time() - start
    logger.info(
        "Backfill complete: %d documents in %.1fs (%.1f docs/sec)",
        embedded,
        elapsed,
        embedded / elapsed if elapsed > 0 else 0,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Backfill embeddings from PostgreSQL documents"
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    backfill(batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
