"""Tests for the Alembic migration runner."""

from tempfile import TemporaryDirectory
from pathlib import Path

from web_search_postgres.migrate import migrate, _get_alembic_dir, _get_migration_files
from web_search_postgres.search import get_connection


class TestGetMigrationFiles:
    def test_finds_revision_files(self):
        files = _get_migration_files()
        assert len(files) >= 1
        assert files[0][0] == 1
        assert files[0][1] == "initial_schema"


class TestGetAlembicDir:
    def test_prefers_env_override(self, monkeypatch):
        with TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir) / "db"
            db_dir.mkdir()
            (db_dir / "alembic.ini").write_text("[alembic]\n")
            monkeypatch.setenv("WEB_SEARCH_DB_DIR", str(db_dir))
            assert _get_alembic_dir() == db_dir


class TestMigrate:
    def test_applies_migrations(self):
        # conftest already ran migrate(), so alembic_version should exist.
        latest_version = f"{_get_migration_files()[-1][0]:03d}"
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT version_num FROM alembic_version")
            rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == latest_version
            cur.close()
        finally:
            conn.close()

    def test_tables_exist(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM documents")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COUNT(*) FROM index_jobs")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COUNT(*) FROM api_keys")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COUNT(*) FROM urls")
            assert cur.fetchone()[0] == 0
            cur.close()
        finally:
            conn.close()

    def test_idempotent(self):
        result = migrate()
        assert result == 0
