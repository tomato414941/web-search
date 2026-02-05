"""
Custom Full-Text Search Indexer

Builds inverted index for fast text search.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from shared.analyzer import analyzer
from shared.db.search import get_connection, is_postgres_mode


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


class SearchIndexer:
    """Builds and maintains the inverted index."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def index_document(
        self,
        url: str,
        title: str,
        content: str,
        conn: Any | None = None,
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

        ph = _placeholder()

        try:
            # 1. Tokenize title and content
            title_tokens = self._tokenize(title)
            content_tokens = self._tokenize(content)

            # 2. Store document metadata
            now = datetime.now(timezone.utc).isoformat()
            cur = conn.cursor()
            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO documents (url, title, content, word_count, indexed_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        word_count = EXCLUDED.word_count,
                        indexed_at = EXCLUDED.indexed_at
                    """,
                    (url, title, content, len(content_tokens), now),
                )
            else:
                cur.execute(
                    f"""
                    INSERT OR REPLACE INTO documents (url, title, content, word_count, indexed_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (url, title, content, len(content_tokens), now),
                )
            cur.close()

            # 3. Clear existing index entries for this document
            cur = conn.cursor()
            cur.execute(f"DELETE FROM inverted_index WHERE url = {ph}", (url,))
            cur.close()

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

    def update_global_stats(self, conn: Any | None = None) -> None:
        """
        Update global index statistics (total docs, avg doc length).
        Call after batch indexing.
        """
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        ph = _placeholder()

        try:
            cur = conn.cursor()

            # Total documents
            cur.execute("SELECT COUNT(*) FROM documents")
            total_docs = cur.fetchone()[0]

            # Average document length
            cur.execute("SELECT AVG(word_count) FROM documents")
            avg_length = cur.fetchone()[0] or 0.0

            # Upsert stats
            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO index_stats (key, value) VALUES ({ph}, {ph})
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ("total_docs", float(total_docs)),
                )
                cur.execute(
                    f"""
                    INSERT INTO index_stats (key, value) VALUES ({ph}, {ph})
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ("avg_doc_length", avg_length),
                )
            else:
                cur.execute(
                    f"INSERT OR REPLACE INTO index_stats (key, value) VALUES ({ph}, {ph})",
                    ("total_docs", float(total_docs)),
                )
                cur.execute(
                    f"INSERT OR REPLACE INTO index_stats (key, value) VALUES ({ph}, {ph})",
                    ("avg_doc_length", avg_length),
                )

            cur.close()

            if should_close:
                conn.commit()

        finally:
            if should_close:
                conn.close()

    def delete_document(self, url: str, conn: Any | None = None) -> None:
        """Remove a document from the index."""
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        ph = _placeholder()

        try:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM documents WHERE url = {ph}", (url,))
            cur.execute(f"DELETE FROM inverted_index WHERE url = {ph}", (url,))
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
        return tokenized.split()

    def _index_field(
        self,
        conn: Any,
        url: str,
        field: str,
        tokens: list[str],
    ) -> None:
        """Build inverted index entries for a field."""
        if not tokens:
            return

        ph = _placeholder()

        # Calculate term frequency and positions
        freq_map: Counter[str] = Counter(tokens)
        pos_map: dict[str, list[int]] = {}

        for i, token in enumerate(tokens):
            if token not in pos_map:
                pos_map[token] = []
            pos_map[token].append(i)

        # Insert into inverted index
        cur = conn.cursor()
        for token, freq in freq_map.items():
            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO inverted_index (token, url, field, term_freq, positions)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT (token, url, field) DO UPDATE SET
                        term_freq = EXCLUDED.term_freq,
                        positions = EXCLUDED.positions
                    """,
                    (token, url, field, freq, json.dumps(pos_map[token])),
                )
            else:
                cur.execute(
                    f"""
                    INSERT OR REPLACE INTO inverted_index (token, url, field, term_freq, positions)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (token, url, field, freq, json.dumps(pos_map[token])),
                )
        cur.close()

    def _update_token_stats(
        self,
        conn: Any,
        url: str,
        tokens: list[str],
    ) -> None:
        """Update document frequency for tokens."""
        unique_tokens = set(tokens)
        ph = _placeholder()

        cur = conn.cursor()
        for token in unique_tokens:
            # Count how many documents contain this token
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT url) FROM inverted_index WHERE token = {ph}
                """,
                (token,),
            )
            doc_freq = cur.fetchone()[0]

            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO token_stats (token, doc_freq) VALUES ({ph}, {ph})
                    ON CONFLICT (token) DO UPDATE SET doc_freq = EXCLUDED.doc_freq
                    """,
                    (token, doc_freq),
                )
            else:
                cur.execute(
                    f"INSERT OR REPLACE INTO token_stats (token, doc_freq) VALUES ({ph}, {ph})",
                    (token, doc_freq),
                )
        cur.close()
