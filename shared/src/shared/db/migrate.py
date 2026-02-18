"""Lightweight numbered-SQL migration runner.

Usage:
    from shared.db.migrate import migrate
    migrate()  # applies pending migrations to the connected PG database

Migrations live in shared/db/migrations/ as numbered SQL files:
    001_initial_schema.sql
    002_add_foreign_keys.sql
    ...

A `schema_version` table tracks which migrations have been applied.
"""

import logging
from pathlib import Path
from typing import Any

from shared.db.search import get_connection, is_postgres_mode, _pg_schema_to_sqlite

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

VERSION_TABLE_PG = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);
"""

VERSION_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    cur.execute(VERSION_TABLE_PG if is_postgres_mode() else VERSION_TABLE_SQLITE)
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
    if is_postgres_mode():
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'documents'
            )
            """
        )
        exists = bool(cur.fetchone()[0])
    else:
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'"
        )
        exists = cur.fetchone() is not None

    if exists and migrations:
        first_version, first_name, _ = migrations[0]
        cur.execute(
            "INSERT INTO schema_version (version, name) VALUES (%s, %s)"
            if is_postgres_mode()
            else "INSERT INTO schema_version (version, name) VALUES (?, ?)",
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

        pg = is_postgres_mode()
        ph = "%s" if pg else "?"

        count = 0
        for version, name, path in migrations:
            if version in applied:
                continue

            sql = path.read_text(encoding="utf-8")

            # Skip PG-only migrations on SQLite
            if not pg and sql.lstrip().startswith("-- pg_only: true"):
                logger.info(
                    "Skipping PG-only migration %03d_%s on SQLite", version, name
                )
                cur = conn.cursor()
                cur.execute(
                    f"INSERT INTO schema_version (version, name) VALUES ({ph}, {ph})",
                    (version, name),
                )
                conn.commit()
                cur.close()
                count += 1
                continue

            logger.info("Applying migration %03d_%s ...", version, name)

            cur = conn.cursor()
            if pg:
                cur.execute(sql)
            else:
                sqlite_sql = _pg_schema_to_sqlite(sql)
                conn.executescript(sqlite_sql)
            conn.commit()

            cur.execute(
                f"INSERT INTO schema_version (version, name) VALUES ({ph}, {ph})",
                (version, name),
            )
            conn.commit()
            cur.close()

            logger.info("Applied migration %03d_%s", version, name)
            count += 1

        return count
    finally:
        conn.close()
