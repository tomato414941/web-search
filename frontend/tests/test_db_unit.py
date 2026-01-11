"""Test SQLite database operations."""

import sqlite3
from frontend.core.db import ensure_db, open_db


class TestDatabaseInitialization:
    """Test database initialization."""

    def test_ensure_db_creates_file(self, test_db_path):
        """ensure_db should create database file."""
        ensure_db(test_db_path)
        import os

        assert os.path.exists(test_db_path)

    def test_ensure_db_creates_tables(self, test_db_path):
        """ensure_db should create required tables."""
        ensure_db(test_db_path)
        conn = sqlite3.connect(test_db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
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

    def test_open_db_returns_connection(self, test_db_path):
        """open_db should return a connection."""
        conn = open_db(test_db_path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()


class TestDocumentOperations:
    """Test document table operations."""

    def test_insert_document(self, test_db_path):
        """Documents can be inserted."""
        conn = open_db(test_db_path)
        conn.execute(
            "INSERT INTO documents (url, title, content, word_count) VALUES (?, ?, ?, ?)",
            ("https://example.com", "Test Page", "This is test content", 4)
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT url, title, content, word_count FROM documents WHERE url = ?",
            ("https://example.com",)
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "https://example.com"
        assert result[1] == "Test Page"
        assert result[2] == "This is test content"
        assert result[3] == 4

    def test_update_document(self, test_db_path):
        """Documents can be updated via upsert pattern."""
        conn = open_db(test_db_path)

        # Insert first version
        conn.execute(
            "INSERT INTO documents (url, title, content) VALUES (?, ?, ?)",
            ("https://example.com", "Original", "Original content")
        )
        conn.commit()

        # Update using upsert pattern
        conn.execute("DELETE FROM documents WHERE url = ?", ("https://example.com",))
        conn.execute(
            "INSERT INTO documents (url, title, content) VALUES (?, ?, ?)",
            ("https://example.com", "Updated", "Updated content")
        )
        conn.commit()

        # Should only have one row
        cursor = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE url = ?", ("https://example.com",)
        )
        count = cursor.fetchone()[0]

        # Get the title
        cursor = conn.execute(
            "SELECT title FROM documents WHERE url = ?", ("https://example.com",)
        )
        title = cursor.fetchone()[0]
        conn.close()

        assert count == 1
        assert title == "Updated"


class TestInvertedIndexOperations:
    """Test inverted index operations."""

    def test_insert_index_entry(self, test_db_path):
        """Index entries can be inserted."""
        conn = open_db(test_db_path)

        conn.execute(
            "INSERT INTO inverted_index (token, url, field, term_freq, positions) VALUES (?, ?, ?, ?, ?)",
            ("python", "https://example.com/python", "title", 2, "[0, 5]")
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT url, term_freq FROM inverted_index WHERE token = ?",
            ("python",)
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "https://example.com/python"
        assert result[1] == 2

    def test_multiple_documents_same_token(self, test_db_path):
        """Multiple documents can share the same token."""
        conn = open_db(test_db_path)

        # Insert multiple entries for same token
        conn.execute(
            "INSERT INTO inverted_index (token, url, field, term_freq) VALUES (?, ?, ?, ?)",
            ("programming", "https://example.com/1", "content", 3)
        )
        conn.execute(
            "INSERT INTO inverted_index (token, url, field, term_freq) VALUES (?, ?, ?, ?)",
            ("programming", "https://example.com/2", "content", 1)
        )
        conn.execute(
            "INSERT INTO inverted_index (token, url, field, term_freq) VALUES (?, ?, ?, ?)",
            ("programming", "https://example.com/3", "title", 1)
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT COUNT(*) FROM inverted_index WHERE token = ?",
            ("programming",)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 3
