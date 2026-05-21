#!/usr/bin/env python3
"""Experimental embedding backfill for existing documents.

This module owns the optional embedding schema so baseline migrations and
baseline services do not need pgvector or OpenAI dependencies.
"""

import argparse
import logging
import os
import sys
import time

import numpy as np
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from web_search_indexing.embedding import _prepare_text, to_pgvector
from web_search_postgres import get_connection
from web_search_postgres.search import sql_placeholder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

MODEL = "text-embedding-3-small"
API_BATCH_SIZE = 100
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _embedding_enrichment_enabled() -> bool:
    return os.environ.get("EMBEDDING_ENRICHMENT_ENABLED", "").strip().lower() in (
        _TRUE_VALUES
    )


def _ensure_embedding_schema() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS page_embeddings (
                url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
                embedding vector(1536)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_page_embeddings_hnsw
                ON page_embeddings USING hnsw (embedding vector_cosine_ops)
            """
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _count_documents_without_embeddings() -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM documents d "
            "LEFT JOIN page_embeddings pe ON d.url = pe.url "
            "WHERE pe.url IS NULL"
        )
        row = cur.fetchone()
        cur.close()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _fetch_documents_without_embeddings(limit: int) -> list[tuple[str, str]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT d.url, d.content FROM documents d "
            "LEFT JOIN page_embeddings pe ON d.url = pe.url "
            "WHERE pe.url IS NULL "
            "ORDER BY d.url LIMIT %s",
            (limit,),
        )
        rows = [(str(url), str(content or "")) for url, content in cur.fetchall()]
        cur.close()
        return rows
    finally:
        conn.close()


def _upsert_embeddings(rows: list[tuple[str, str]]) -> None:
    if not rows:
        return
    ph = sql_placeholder()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            f"""
            INSERT INTO page_embeddings (url, embedding) VALUES ({ph}, {ph})
            ON CONFLICT (url) DO UPDATE SET embedding = EXCLUDED.embedding
            """,
            rows,
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API with retry."""
    prepared = [_prepare_text(text) for text in texts]
    response = client.embeddings.create(input=prepared, model=MODEL)
    sorted_data = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in sorted_data]


def backfill(
    batch_size: int = 50,
    dry_run: bool = False,
) -> None:
    if not _embedding_enrichment_enabled():
        logger.error("EMBEDDING_ENRICHMENT_ENABLED=true is required")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)

    if not os.environ.get("DATABASE_URL", ""):
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    _ensure_embedding_schema()
    pending = _count_documents_without_embeddings()
    logger.info("Documents without embeddings: %d", pending)

    if pending == 0:
        logger.info("All documents already have embeddings, skipping")
        return

    if dry_run:
        logger.info("Dry run - exiting")
        return

    client = OpenAI(api_key=api_key)
    embedded = 0
    start = time.time()

    while True:
        rows = _fetch_documents_without_embeddings(batch_size)
        if not rows:
            break

        urls = [url for url, _ in rows]
        contents = [content for _, content in rows]

        for index in range(0, len(contents), API_BATCH_SIZE):
            chunk_urls = urls[index : index + API_BATCH_SIZE]
            chunk_contents = contents[index : index + API_BATCH_SIZE]

            try:
                vectors = _embed_batch(client, chunk_contents)
            except Exception as exc:
                logger.error("Best-effort embedding backfill failed, stopping: %s", exc)
                sys.exit(1)

            batch_rows = []
            for url, vector_list in zip(chunk_urls, vectors):
                vector = np.array(vector_list, dtype=np.float32)
                batch_rows.append((url, to_pgvector(vector)))

            _upsert_embeddings(batch_rows)
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

    elapsed = time.time() - start
    logger.info(
        "Backfill complete: %d documents in %.1fs (%.1f docs/sec)",
        embedded,
        elapsed,
        embedded / elapsed if elapsed > 0 else 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill experimental embeddings from PostgreSQL documents"
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    backfill(batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
