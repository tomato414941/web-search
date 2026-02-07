#!/usr/bin/env python3
"""
Re-index all documents with updated analyzer.

Reads all documents from the database, re-tokenizes with the current
analyzer (including lowercase normalization and stop word filtering),
and rebuilds the inverted_index and token_stats tables.

Usage:
    # SQLite (local dev)
    python scripts/reindex.py

    # PostgreSQL (production)
    DATABASE_URL=postgresql://... python scripts/reindex.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.db.search import get_connection, is_postgres_mode
from shared.search.indexer import SearchIndexer


def main():
    db_path = os.getenv("SEARCH_DB", "/data/search.db")
    postgres = is_postgres_mode()
    print(f"Database mode: {'PostgreSQL' if postgres else 'SQLite'}")

    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        total = cur.fetchone()[0]
        cur.close()
        print(f"Total documents to re-index: {total}")

        if total == 0:
            print("No documents found. Exiting.")
            return

        # Clear existing index
        print("Clearing inverted_index and token_stats...")
        cur = conn.cursor()
        cur.execute("DELETE FROM inverted_index")
        cur.execute("DELETE FROM token_stats")
        conn.commit()
        cur.close()

        # Re-index in batches
        indexer = SearchIndexer(db_path)
        batch_size = 500
        processed = 0

        cur = conn.cursor()
        cur.execute("SELECT url, title, content FROM documents")

        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break

            batch_conn = get_connection(db_path)
            try:
                for url, title, content in rows:
                    try:
                        indexer.index_document(
                            url, title or "", content or "", batch_conn
                        )
                    except Exception as e:
                        print(f"  Error indexing {url}: {e}")

                batch_conn.commit()
            finally:
                batch_conn.close()

            processed += len(rows)
            print(f"  Processed {processed}/{total} documents...")

        cur.close()

        # Update global stats
        print("Updating global stats...")
        indexer.update_global_stats()

        print(f"Done: {processed} documents re-indexed.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
