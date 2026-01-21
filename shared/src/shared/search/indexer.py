"""
Custom Full-Text Search Indexer

Builds inverted index for fast text search.
"""

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from shared.analyzer import analyzer
from shared.db.search import get_connection


class SearchIndexer:
    """Builds and maintains the inverted index."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def index_document(
        self,
        url: str,
        title: str,
        content: str,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """
        Index a document into the custom search engine.

        Args:
            url: Document URL (primary key)
            title: Document title
            content: Document content
            conn: Optional existing connection (for batch operations)
        """
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        try:
            # 1. Tokenize title and content
            title_tokens = self._tokenize(title)
            content_tokens = self._tokenize(content)

            # 2. Store document metadata
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (url, title, content, word_count, indexed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (url, title, content, len(content_tokens), now),
            )

            # 3. Clear existing index entries for this document
            conn.execute("DELETE FROM inverted_index WHERE url = ?", (url,))

            # 4. Build inverted index for title
            self._index_field(conn, url, "title", title_tokens)

            # 5. Build inverted index for content
            self._index_field(conn, url, "content", content_tokens)

            # 6. Update token statistics (document frequency)
            self._update_token_stats(conn, url, title_tokens + content_tokens)

            if should_close:
                conn.commit()

        finally:
            if should_close:
                conn.close()

    def update_global_stats(self, conn: sqlite3.Connection | None = None) -> None:
        """
        Update global index statistics (total docs, avg doc length).
        Call after batch indexing.
        """
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        try:
            # Total documents
            total_docs = conn.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0]

            # Average document length
            avg_length = conn.execute(
                "SELECT AVG(word_count) FROM documents"
            ).fetchone()[0] or 0.0

            # Upsert stats
            conn.execute(
                "INSERT OR REPLACE INTO index_stats (key, value) VALUES (?, ?)",
                ("total_docs", float(total_docs)),
            )
            conn.execute(
                "INSERT OR REPLACE INTO index_stats (key, value) VALUES (?, ?)",
                ("avg_doc_length", avg_length),
            )

            if should_close:
                conn.commit()

        finally:
            if should_close:
                conn.close()

    def delete_document(self, url: str, conn: sqlite3.Connection | None = None) -> None:
        """Remove a document from the index."""
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        try:
            conn.execute("DELETE FROM documents WHERE url = ?", (url,))
            conn.execute("DELETE FROM inverted_index WHERE url = ?", (url,))

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
        return tokenized.split()

    def _index_field(
        self,
        conn: sqlite3.Connection,
        url: str,
        field: str,
        tokens: list[str],
    ) -> None:
        """Build inverted index entries for a field."""
        if not tokens:
            return

        # Calculate term frequency and positions
        freq_map: Counter[str] = Counter(tokens)
        pos_map: dict[str, list[int]] = {}

        for i, token in enumerate(tokens):
            if token not in pos_map:
                pos_map[token] = []
            pos_map[token].append(i)

        # Insert into inverted index
        for token, freq in freq_map.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO inverted_index (token, url, field, term_freq, positions)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token, url, field, freq, json.dumps(pos_map[token])),
            )

    def _update_token_stats(
        self,
        conn: sqlite3.Connection,
        url: str,
        tokens: list[str],
    ) -> None:
        """Update document frequency for tokens."""
        unique_tokens = set(tokens)

        for token in unique_tokens:
            # Count how many documents contain this token
            doc_freq = conn.execute(
                """
                SELECT COUNT(DISTINCT url) FROM inverted_index WHERE token = ?
                """,
                (token,),
            ).fetchone()[0]

            conn.execute(
                "INSERT OR REPLACE INTO token_stats (token, doc_freq) VALUES (?, ?)",
                (token, doc_freq),
            )
