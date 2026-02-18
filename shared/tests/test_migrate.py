"""Tests for the migration runner."""

import sqlite3
from unittest.mock import patch


from shared.db.migrate import migrate, _get_migration_files


class TestGetMigrationFiles:
    def test_finds_sql_files(self):
        files = _get_migration_files()
        assert len(files) >= 2
        assert files[0][0] == 1
        assert files[0][1] == "initial_schema"
        assert files[1][0] == 2
        assert files[1][1] == "add_foreign_keys"


class TestMigrate:
    def test_fresh_db_applies_all(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        # Create empty DB
        sqlite3.connect(db_path).close()

        with patch("shared.db.migrate.is_postgres_mode", return_value=False):
            count = migrate(db_path)

        # 001 has IF NOT EXISTS so it works on fresh DB
        # 002 uses PG-only DO $$ block, so it will fail on SQLite
        # For fresh DB: 001 applied directly (not backfilled since no tables exist)
        assert count >= 1

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT version, name FROM schema_version ORDER BY version")
        rows = cur.fetchall()
        assert len(rows) >= 1
        assert rows[0] == (1, "initial_schema")

        # Verify tables were created
        cur.execute("SELECT COUNT(*) FROM documents")
        assert cur.fetchone()[0] == 0
        conn.close()

    def test_existing_db_backfills_001(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE documents (url TEXT PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE schema_version "
            "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()
        conn.close()

        with patch("shared.db.migrate.is_postgres_mode", return_value=False):
            migrate(db_path)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_version ORDER BY version")
        versions = [row[0] for row in cur.fetchall()]
        # 001 should be backfilled
        assert 1 in versions
        conn.close()

    def test_idempotent(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        sqlite3.connect(db_path).close()

        with patch("shared.db.migrate.is_postgres_mode", return_value=False):
            migrate(db_path)
            count2 = migrate(db_path)

        # Second run should apply 0 new migrations
        assert count2 == 0
