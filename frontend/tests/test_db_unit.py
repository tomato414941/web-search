"""Test PostgreSQL database operations."""

from shared.postgres.search import get_connection


class TestDocumentOperations:
    """Test document table operations."""

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
