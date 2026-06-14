"""Tests for the Alembic migration runner."""

from tempfile import TemporaryDirectory
from pathlib import Path

from web_search_postgres.migrate import migrate, _get_alembic_dir
from web_search_postgres.search import get_connection


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
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT version_num FROM alembic_version")
            rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "012"
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
            cur.execute("SELECT COUNT(*) FROM urls")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COUNT(*) FROM crawl_schedule")
            assert cur.fetchone()[0] == 0
            cur.close()
        finally:
            conn.close()

    def test_urls_schema_is_discovery_ledger_only(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'urls'
                ORDER BY ordinal_position
                """
            )
            columns = [row[0] for row in cur.fetchall()]
            assert columns == [
                "url_hash",
                "url",
                "domain",
                "created_at",
            ]
            cur.close()
        finally:
            conn.close()

    def test_crawl_schedule_schema_does_not_store_discovery_route(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'crawl_schedule'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "discovered_via" not in columns
            cur.close()
        finally:
            conn.close()

    def test_crawl_schedule_schema_does_not_store_unused_fetch_metadata(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'crawl_schedule'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "etag" not in columns
            assert "last_modified" not in columns
            assert "content_hash" not in columns
            cur.close()
        finally:
            conn.close()

    def test_index_jobs_schema_does_not_store_content_hash(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'index_jobs'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "content_hash" not in columns
            assert "dedupe_key" in columns
            cur.close()
        finally:
            conn.close()

    def test_crawl_schedule_schema_does_not_store_redundant_normalized_url(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'crawl_schedule'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "normalized_url" not in columns
            cur.close()
        finally:
            conn.close()

    def test_crawl_schedule_schema_does_not_store_discovery_depth(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'crawl_schedule'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "discovery_depth" not in columns
            cur.close()
        finally:
            conn.close()

    def test_crawl_schedule_schema_does_not_store_priority_score(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'crawl_schedule'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "priority_score" not in columns
            cur.close()
        finally:
            conn.close()

    def test_idempotent(self):
        result = migrate()
        assert result == 0
