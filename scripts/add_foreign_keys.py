"""Add FK constraints to documents-dependent tables.

Cleans up orphan rows, then adds FOREIGN KEY ... ON DELETE CASCADE.
Idempotent — safe to run multiple times.

Usage:
    DATABASE_URL=postgres://... python scripts/add_foreign_keys.py
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.db.search import get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

FK_TABLES = ["page_embeddings", "page_ranks"]
FK_CONSTRAINT_PREFIX = "fk_{table}_documents"
BATCH_SIZE = 10_000


def _constraint_exists(cur, table: str) -> bool:
    constraint_name = FK_CONSTRAINT_PREFIX.format(table=table)
    cur.execute(
        """
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = %s AND table_name = %s
        """,
        (constraint_name, table),
    )
    return cur.fetchone() is not None


def _cleanup_orphans(cur, table: str) -> int:
    total_deleted = 0
    while True:
        cur.execute(
            f"""
            DELETE FROM {table}
            WHERE ctid IN (
                SELECT t.ctid FROM {table} t
                LEFT JOIN documents d ON d.url = t.url
                WHERE d.url IS NULL
                LIMIT %s
            )
            """,
            (BATCH_SIZE,),
        )
        deleted = cur.rowcount
        total_deleted += deleted
        if deleted > 0:
            logger.info(
                "  deleted %d orphan rows from %s (total: %d)",
                deleted,
                table,
                total_deleted,
            )
        if deleted < BATCH_SIZE:
            break
    return total_deleted


def _add_fk(cur, table: str) -> None:
    constraint_name = FK_CONSTRAINT_PREFIX.format(table=table)
    cur.execute(
        f"""
        ALTER TABLE {table}
        ADD CONSTRAINT {constraint_name}
        FOREIGN KEY (url) REFERENCES documents(url) ON DELETE CASCADE
        """
    )
    logger.info("  added FK constraint %s", constraint_name)


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL is required")
        sys.exit(1)

    conn = get_connection()
    try:
        cur = conn.cursor()

        for table in FK_TABLES:
            logger.info("Processing %s ...", table)

            if _constraint_exists(cur, table):
                logger.info("  FK already exists, skipping")
                conn.commit()
                continue

            deleted = _cleanup_orphans(cur, table)
            conn.commit()
            if deleted > 0:
                logger.info("  cleaned up %d total orphan rows", deleted)

            _add_fk(cur, table)
            conn.commit()

        # Verify
        for table in FK_TABLES:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM {table} t
                LEFT JOIN documents d ON d.url = t.url
                WHERE d.url IS NULL
                """
            )
            orphans = cur.fetchone()[0]
            if orphans > 0:
                logger.error("  FAIL: %d orphan rows remain in %s", orphans, table)
            else:
                logger.info("  OK: %s has 0 orphan rows", table)

        cur.close()
    finally:
        conn.close()

    logger.info("Done.")


if __name__ == "__main__":
    main()
