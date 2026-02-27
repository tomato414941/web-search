"""Lightweight numbered-SQL migration runner.

Usage:
    from shared.postgres.migrate import migrate
    migrate()  # applies pending migrations to the connected PG database

Migrations live in shared/postgres/migrations/ as numbered SQL files:
    001_initial_schema.sql
    002_add_foreign_keys.sql
    ...

A `schema_version` table tracks which migrations have been applied.
"""

import logging
import re
from pathlib import Path
from typing import Any

from shared.postgres.search import get_connection

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);
"""


def _get_migration_files() -> list[tuple[int, str, Path]]:
    files: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        parts = path.stem.split("_", 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        version = int(parts[0])
        name = parts[1]
        files.append((version, name, path))
    return files


def _ensure_version_table(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute(VERSION_TABLE)
    conn.commit()
    cur.close()


def _get_applied_versions(conn: Any) -> set[int]:
    cur = conn.cursor()
    cur.execute("SELECT version FROM schema_version")
    versions = {row[0] for row in cur.fetchall()}
    cur.close()
    return versions


def _backfill_existing_db(conn: Any, migrations: list[tuple[int, str, Path]]) -> None:
    """Mark migration 001 as applied if tables already exist (pre-migration DB)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'documents'
        )
        """
    )
    exists = bool(cur.fetchone()[0])

    if exists and migrations:
        first_version, first_name, _ = migrations[0]
        cur.execute(
            "INSERT INTO schema_version (version, name) VALUES (%s, %s)",
            (first_version, first_name),
        )
        conn.commit()
        logger.info(
            "Backfilled migration %03d_%s (existing DB)", first_version, first_name
        )

    cur.close()


def migrate(db_path: str | None = None) -> int:
    """Run pending migrations. Returns count of migrations applied."""
    migrations = _get_migration_files()
    if not migrations:
        return 0

    conn = get_connection(db_path)
    try:
        _ensure_version_table(conn)

        applied = _get_applied_versions(conn)

        # Backfill for existing databases
        if not applied:
            _backfill_existing_db(conn, migrations)
            applied = _get_applied_versions(conn)

        count = 0
        for version, name, path in migrations:
            if version in applied:
                continue

            sql = path.read_text(encoding="utf-8")

            logger.info("Applying migration %03d_%s ...", version, name)

            needs_autocommit = bool(
                re.search(r"CREATE\s+INDEX\s+CONCURRENTLY", sql, re.IGNORECASE)
            )

            try:
                if needs_autocommit:
                    # CONCURRENTLY cannot run inside a transaction block.
                    # Access the underlying psycopg2 connection for autocommit.
                    raw = getattr(conn, "_conn", conn)
                    old_autocommit = raw.autocommit
                    raw.autocommit = True
                    try:
                        cur = raw.cursor()
                        cur.execute(sql)
                        cur.close()
                    finally:
                        raw.autocommit = old_autocommit
                else:
                    cur = conn.cursor()
                    cur.execute(sql)
                    conn.commit()
                    cur.close()
            except Exception as exc:
                conn.rollback()
                logger.warning(
                    "Migration %03d_%s failed (skipped): %s", version, name, exc
                )
                continue

            cur = conn.cursor()
            cur.execute(
                "INSERT INTO schema_version (version, name) VALUES (%s, %s)",
                (version, name),
            )
            conn.commit()
            cur.close()

            logger.info("Applied migration %03d_%s", version, name)
            count += 1

        return count
    finally:
        conn.close()
