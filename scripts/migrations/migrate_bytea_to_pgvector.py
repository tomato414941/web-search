#!/usr/bin/env python3
"""Migrate page_embeddings from BYTEA to pgvector vector(1536).

Run this ONCE after upgrading the postgres image to pgvector/pgvector:pg16
and before deploying the new application code.

Usage:
    DATABASE_URL=postgresql://... python3 scripts/migrate_bytea_to_pgvector.py
"""

import os
import struct
import sys


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is required")
        sys.exit(1)

    import psycopg2

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    # 1. Ensure pgvector extension
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    print("pgvector extension ensured")

    # 2. Check current column type
    cur.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'page_embeddings' AND column_name = 'embedding'
    """)
    row = cur.fetchone()
    if not row:
        print("page_embeddings table or embedding column not found, skipping migration")
        conn.close()
        return

    col_type = row[0]
    if col_type == "USER-DEFINED":
        print("embedding column is already vector type, no migration needed")
        conn.close()
        return

    print(f"Current embedding column type: {col_type}")

    # 3. Count rows
    cur.execute("SELECT COUNT(*) FROM page_embeddings WHERE embedding IS NOT NULL")
    total = cur.fetchone()[0]
    print(f"Rows to migrate: {total}")

    if total == 0:
        # No data — just alter column directly
        cur.execute("ALTER TABLE page_embeddings DROP COLUMN embedding")
        cur.execute("ALTER TABLE page_embeddings ADD COLUMN embedding vector(1536)")
        conn.commit()
        print("Column type changed to vector(1536) (no data migration needed)")
        conn.close()
        return

    # 4. Add new vector column
    cur.execute("ALTER TABLE page_embeddings ADD COLUMN embedding_vec vector(1536)")
    conn.commit()
    print("Added temporary embedding_vec column")

    # 5. Migrate in batches using offset/limit to avoid cursor invalidation
    batch_size = 500
    migrated = 0

    while migrated < total:
        cur.execute(
            "SELECT url, embedding FROM page_embeddings "
            "WHERE embedding IS NOT NULL AND embedding_vec IS NULL "
            "LIMIT %s",
            (batch_size,),
        )
        rows = cur.fetchall()
        if not rows:
            break

        for url, blob in rows:
            if isinstance(blob, memoryview):
                blob = bytes(blob)
            n = len(blob) // 4
            values = struct.unpack(f"{n}f", blob)
            vec_str = "[" + ",".join(f"{v:.8g}" for v in values) + "]"

            cur.execute(
                "UPDATE page_embeddings SET embedding_vec = %s::vector WHERE url = %s",
                (vec_str, url),
            )

        migrated += len(rows)
        conn.commit()
        print(f"  Migrated {migrated}/{total} rows")

    # 6. Swap columns
    cur.execute("ALTER TABLE page_embeddings DROP COLUMN embedding")
    cur.execute("ALTER TABLE page_embeddings RENAME COLUMN embedding_vec TO embedding")
    conn.commit()
    print("Swapped columns")

    # 7. Create HNSW index
    print("Creating HNSW index (this may take a moment)...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_page_embeddings_hnsw
        ON page_embeddings USING hnsw (embedding vector_cosine_ops)
    """)
    conn.commit()
    print("HNSW index created")

    cur.close()
    conn.close()
    print(f"Migration complete: {migrated} embeddings migrated to pgvector")


if __name__ == "__main__":
    main()
