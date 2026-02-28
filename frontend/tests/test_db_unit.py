"""Test PostgreSQL database operations."""

from shared.db.search import get_connection


class TestDatabaseInitialization:
    """Test database initialization (schema created by Alembic in conftest)."""

    def test_tables_exist(self):
        """Required tables should exist (created by Alembic migrations)."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            tables = {row[0] for row in cur.fetchall()}
            cur.close()
        finally:
            conn.close()

        # Core tables
        assert "documents" in tables

        # Other tables
        assert "links" in tables
        assert "page_ranks" in tables
        assert "page_embeddings" in tables

    def test_get_connection_returns_connection(self):
        """get_connection should return a usable connection."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
            cur.close()
        finally:
            conn.close()


class TestDocumentOperations:
    """Test document table operations."""

    def test_insert_document(self):
        """Documents can be inserted."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (url, title, content, word_count) VALUES (%s, %s, %s, %s)",
                ("https://example.com", "Test Page", "This is test content", 4),
            )
            conn.commit()

            cur.execute(
                "SELECT url, title, content, word_count FROM documents WHERE url = %s",
                ("https://example.com",),
            )
            result = cur.fetchone()
            cur.close()
        finally:
            conn.close()

        assert result is not None
        assert result[0] == "https://example.com"
        assert result[1] == "Test Page"
        assert result[2] == "This is test content"
        assert result[3] == 4

    def test_update_document(self):
        """Documents can be updated via upsert pattern."""
        conn = get_connection()
        try:
            cur = conn.cursor()

            # Insert first version
            cur.execute(
                "INSERT INTO documents (url, title, content) VALUES (%s, %s, %s)",
                ("https://example.com", "Original", "Original content"),
            )
            conn.commit()

            # Update using upsert pattern
            cur.execute(
                "DELETE FROM documents WHERE url = %s", ("https://example.com",)
            )
            cur.execute(
                "INSERT INTO documents (url, title, content) VALUES (%s, %s, %s)",
                ("https://example.com", "Updated", "Updated content"),
            )
            conn.commit()

            # Should only have one row
            cur.execute(
                "SELECT COUNT(*) FROM documents WHERE url = %s",
                ("https://example.com",),
            )
            count = cur.fetchone()[0]

            # Get the title
            cur.execute(
                "SELECT title FROM documents WHERE url = %s", ("https://example.com",)
            )
            title = cur.fetchone()[0]
            cur.close()
        finally:
            conn.close()

        assert count == 1
        assert title == "Updated"
