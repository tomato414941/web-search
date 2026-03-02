"""
Document Indexer

Writes document metadata to the documents table.
Search indexing is handled by OpenSearch via dual-write.
"""

from datetime import datetime, timezone
from typing import Any

from shared.search_kernel.analyzer import analyzer, STOP_WORDS
from shared.postgres.search import get_connection, sql_placeholder


class SearchIndexer:
    """Indexes documents into the documents table."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def index_document(
        self,
        url: str,
        title: str,
        content: str,
        conn: Any | None = None,
        published_at: str | None = None,
    ) -> None:
        """Index a document into the documents table.

        Args:
            url: Document URL (primary key)
            title: Document title
            content: Document content
            conn: Optional existing connection (for batch operations)
            published_at: ISO 8601 publication date from HTML metadata
        """
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        ph = sql_placeholder()

        try:
            content_tokens = self._tokenize(content)

            now = datetime.now(timezone.utc).isoformat()
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO documents (url, title, content, word_count, indexed_at, published_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    word_count = EXCLUDED.word_count,
                    indexed_at = EXCLUDED.indexed_at,
                    published_at = COALESCE(EXCLUDED.published_at, documents.published_at)
                """,
                (url, title, content, len(content_tokens), now, published_at),
            )
            cur.close()

            if should_close:
                conn.commit()

        finally:
            if should_close:
                conn.close()

    def delete_document(self, url: str, conn: Any | None = None) -> None:
        """Remove a document from the database."""
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        ph = sql_placeholder()

        try:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM documents WHERE url = {ph}", (url,))
            cur.close()

            if should_close:
                conn.commit()

        finally:
            if should_close:
                conn.close()

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text using SudachiPy analyzer."""
        if not text:
            return []
        tokenized = analyzer.tokenize(text)
        return [t for t in tokenized.split() if len(t) > 1 and t not in STOP_WORDS]
