"""
Document Indexer

Writes document metadata to the documents table.
Search indexing is handled by OpenSearch via dual-write.
"""

from datetime import datetime, timezone
from typing import Any

from web_search_postgres.repositories import DocumentRepository
from web_search_postgres import get_connection


class SearchIndexer:
    """Indexes documents into the documents table."""

    def index_document(
        self,
        url: str,
        title: str,
        content: str,
        conn: Any | None = None,
    ) -> None:
        """Index a document into the documents table.

        Args:
            url: Document URL (primary key)
            title: Document title
            content: Document content
            conn: Optional existing connection (for batch operations)
        """
        should_close = conn is None
        if conn is None:
            conn = get_connection()

        try:
            DocumentRepository.upsert_document(
                conn,
                url=url,
                title=title,
                content=content,
                indexed_at=datetime.now(timezone.utc).isoformat(),
            )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def delete_document(self, url: str, conn: Any | None = None) -> None:
        """Remove a document from the database."""
        should_close = conn is None
        if conn is None:
            conn = get_connection()

        try:
            DocumentRepository.delete_by_url(conn, url)
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()
