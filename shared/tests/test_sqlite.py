"""Test SQLite database operations."""

import sqlite3
from shared.db.sqlite import ensure_db, open_db, upsert_page


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

        # Should have these tables
        assert "pages" in tables
        assert "links" in tables
        assert "page_ranks" in tables
        assert "page_embeddings" in tables

    def test_open_db_returns_connection(self, test_db_path):
        """open_db should return a connection."""
        conn = open_db(test_db_path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()


class TestPageOperations:
    """Test page insertion and updates."""

    def test_upsert_page_inserts(self, test_db_path):
        """upsert_page should insert new pages."""
        conn = open_db(test_db_path)
        upsert_page(
            conn,
            "https://example.com",
            "Test Page",
            "This is test content",
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT url, title FROM pages WHERE url = ?", ("https://example.com",)
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "https://example.com"
        assert result[1] == "Test Page"

    def test_upsert_page_updates_existing(self, test_db_path):
        """upsert_page should update existing pages."""
        conn = open_db(test_db_path)

        # Insert first version
        upsert_page(conn, "https://example.com", "Original", "Original content")
        conn.commit()

        # Update
        upsert_page(conn, "https://example.com", "Updated", "Updated content")
        conn.commit()

        # Should only have one row
        cursor = conn.execute(
            "SELECT COUNT(*) FROM pages WHERE url = ?", ("https://example.com",)
        )
        count = cursor.fetchone()[0]

        # Get the title
        cursor = conn.execute(
            "SELECT title FROM pages WHERE url = ?", ("https://example.com",)
        )
        title = cursor.fetchone()[0]
        conn.close()

        assert count == 1
        assert title == "Updated"

    def test_upsert_with_tokenized_content(self, test_db_path):
        """upsert_page should store both raw and tokenized content."""
        conn = open_db(test_db_path)
        upsert_page(
            conn,
            "https://example.com",
            "tokenized title",
            "tokenized content",
            raw_title="Raw Title",
            raw_content="Raw Content",
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT title, content, raw_title, raw_content FROM pages WHERE url = ?",
            ("https://example.com",),
        )
        result = cursor.fetchone()
        conn.close()

        assert result[0] == "tokenized title"  # FTS indexed
        assert result[1] == "tokenized content"  # FTS indexed
        assert result[2] == "Raw Title"  # Original
        assert result[3] == "Raw Content"  # Original

    def test_fts5_search_works(self, test_db_path):
        """FTS5 search should find matching pages."""
        conn = open_db(test_db_path)

        # Insert multiple pages
        upsert_page(
            conn,
            "https://example.com/python",
            "Python Guide",
            "Learn Python programming",
        )
        upsert_page(
            conn, "https://example.com/java", "Java Guide", "Learn Java programming"
        )
        upsert_page(
            conn,
            "https://example.com/rust",
            "Rust Guide",
            "Learn Rust systems programming",
        )
        conn.commit()

        # Search for "Python"
        cursor = conn.execute("SELECT url FROM pages WHERE pages MATCH ?", ("Python",))
        results = cursor.fetchall()
        conn.close()

        assert len(results) == 1
        assert results[0][0] == "https://example.com/python"

    def test_fts5_search_multiple_results(self, test_db_path):
        """FTS5 should return multiple matching results."""
        conn = open_db(test_db_path)

        upsert_page(
            conn, "https://example.com/1", "Programming in Python", "Python basics"
        )
        upsert_page(
            conn, "https://example.com/2", "Advanced Programming", "Python advanced"
        )
        upsert_page(
            conn, "https://example.com/3", "Web Development", "JavaScript and HTML"
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT url FROM pages WHERE pages MATCH ?", ("Programming",)
        )
        results = cursor.fetchall()
        conn.close()

        assert len(results) == 2  # First two pages
