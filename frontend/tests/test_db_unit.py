"""Test PostgreSQL database operations."""

from shared.postgres.search import ensure_db, get_connection


class TestDatabaseInitialization:
    """Test database initialization."""

    def test_ensure_db_creates_tables(self):
        """ensure_db should create required tables."""
        ensure_db()
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

        # Custom search tables
        assert "documents" in tables
        assert "inverted_index" in tables
        assert "index_stats" in tables
        assert "token_stats" in tables

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


class TestInvertedIndexOperations:
    """Test inverted index operations."""

    def test_insert_index_entry(self):
        """Index entries can be inserted."""
        conn = get_connection()
        try:
            cur = conn.cursor()

            # Need a document first (foreign key)
            cur.execute(
                "INSERT INTO documents (url, title, content) VALUES (%s, %s, %s)",
                ("https://example.com/python", "Python", "content"),
            )

            cur.execute(
                "INSERT INTO inverted_index (token, url, field, term_freq, positions) VALUES (%s, %s, %s, %s, %s)",
                ("python", "https://example.com/python", "title", 2, "[0, 5]"),
            )
            conn.commit()

            cur.execute(
                "SELECT url, term_freq FROM inverted_index WHERE token = %s",
                ("python",),
            )
            result = cur.fetchone()
            cur.close()
        finally:
            conn.close()

        assert result is not None
        assert result[0] == "https://example.com/python"
        assert result[1] == 2

    def test_multiple_documents_same_token(self):
        """Multiple documents can share the same token."""
        conn = get_connection()
        try:
            cur = conn.cursor()

            # Insert parent documents first (foreign key)
            for i in range(1, 4):
                cur.execute(
                    "INSERT INTO documents (url, title, content) VALUES (%s, %s, %s)",
                    (f"https://example.com/{i}", "Test", "content"),
                )

            # Insert multiple entries for same token
            cur.execute(
                "INSERT INTO inverted_index (token, url, field, term_freq) VALUES (%s, %s, %s, %s)",
                ("programming", "https://example.com/1", "content", 3),
            )
            cur.execute(
                "INSERT INTO inverted_index (token, url, field, term_freq) VALUES (%s, %s, %s, %s)",
                ("programming", "https://example.com/2", "content", 1),
            )
            cur.execute(
                "INSERT INTO inverted_index (token, url, field, term_freq) VALUES (%s, %s, %s, %s)",
                ("programming", "https://example.com/3", "title", 1),
            )
            conn.commit()

            cur.execute(
                "SELECT COUNT(*) FROM inverted_index WHERE token = %s", ("programming",)
            )
            count = cur.fetchone()[0]
            cur.close()
        finally:
            conn.close()

        assert count == 3
