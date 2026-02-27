from shared.postgres.search import get_connection


def test_db_creation():
    """Verify that database creates required tables."""
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

    # Custom search engine tables
    assert "documents" in tables
    assert "inverted_index" in tables
    assert "index_stats" in tables
    assert "token_stats" in tables

    # Link graph tables
    assert "links" in tables
    assert "page_ranks" in tables
    assert "page_embeddings" in tables

    # Analytics tables
    assert "search_logs" in tables
    assert "search_events" in tables


def test_documents_table_schema():
    """Verify documents table has correct columns."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO documents (url, title, content, word_count, indexed_at) VALUES (%s, %s, %s, %s, %s)",
            (
                "http://example.com",
                "Test Title",
                "Test Content",
                2,
                "2024-01-01T00:00:00",
            ),
        )
        conn.commit()

        cur.execute(
            "SELECT url, title, content, word_count, indexed_at FROM documents WHERE url = %s",
            ("http://example.com",),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "http://example.com"
    assert row[1] == "Test Title"
    assert row[2] == "Test Content"
    assert row[3] == 2


def test_inverted_index_table_schema():
    """Verify inverted_index table has correct columns."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Need parent document for FK
        cur.execute(
            "INSERT INTO documents (url, title, content) VALUES (%s, %s, %s)",
            ("http://example.com", "Test", "content"),
        )
        cur.execute(
            "INSERT INTO inverted_index (token, url, field, term_freq, positions) VALUES (%s, %s, %s, %s, %s)",
            ("test", "http://example.com", "title", 1, "[0]"),
        )
        conn.commit()

        cur.execute(
            "SELECT token, url, field, term_freq, positions FROM inverted_index WHERE token = %s",
            ("test",),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "test"
    assert row[1] == "http://example.com"
    assert row[2] == "title"
    assert row[3] == 1
    assert row[4] == "[0]"
