import sqlite3
import pytest
from frontend.core.db import open_db


def test_db_creation():
    """Verify that database creates required tables."""
    con = open_db(":memory:")
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = {row[0] for row in cur.fetchall()}

    # Custom search engine tables
    assert "documents" in tables
    assert "inverted_index" in tables
    assert "index_stats" in tables
    assert "token_stats" in tables

    # Link graph tables
    assert "links" in tables
    assert "page_ranks" in tables
    assert "page_embeddings" in tables

    con.close()


def test_documents_table_schema():
    """Verify documents table has correct columns."""
    con = open_db(":memory:")

    # Insert a test document
    con.execute(
        "INSERT INTO documents (url, title, content, word_count, indexed_at) VALUES (?, ?, ?, ?, ?)",
        ("http://example.com", "Test Title", "Test Content", 2, "2024-01-01T00:00:00")
    )
    con.commit()

    row = con.execute(
        "SELECT url, title, content, word_count, indexed_at FROM documents WHERE url = ?",
        ("http://example.com",)
    ).fetchone()

    assert row is not None
    assert row[0] == "http://example.com"
    assert row[1] == "Test Title"
    assert row[2] == "Test Content"
    assert row[3] == 2
    assert row[4] == "2024-01-01T00:00:00"

    con.close()


def test_inverted_index_table_schema():
    """Verify inverted_index table has correct columns."""
    con = open_db(":memory:")

    # Insert a test entry
    con.execute(
        "INSERT INTO inverted_index (token, url, field, term_freq, positions) VALUES (?, ?, ?, ?, ?)",
        ("test", "http://example.com", "title", 1, "[0]")
    )
    con.commit()

    row = con.execute(
        "SELECT token, url, field, term_freq, positions FROM inverted_index WHERE token = ?",
        ("test",)
    ).fetchone()

    assert row is not None
    assert row[0] == "test"
    assert row[1] == "http://example.com"
    assert row[2] == "title"
    assert row[3] == 1
    assert row[4] == "[0]"

    con.close()
