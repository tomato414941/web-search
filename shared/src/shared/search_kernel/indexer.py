"""
Custom Full-Text Search Indexer

Builds inverted index for fast text search.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from shared.search_kernel.analyzer import analyzer, STOP_WORDS
from shared.postgres.search import get_connection, is_postgres_mode, sql_placeholder


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

        ph = sql_placeholder()

        try:
            # 1. Tokenize title and content
            title_tokens = self._tokenize(title)
            content_tokens = self._tokenize(content)

            # 2. Store document metadata
            now = datetime.now(timezone.utc).isoformat()
            cur = conn.cursor()
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
            cur.close()

            # 3. Get tokens from old version (for incremental stats update)
            cur = conn.cursor()
            old_tokens: set[str] = set()
            if is_postgres_mode():
                cur.execute(
                    f"SELECT DISTINCT token FROM inverted_index WHERE url = {ph}",
                    (url,),
                )
                old_tokens = {row[0] for row in cur.fetchall()}

            # Clear existing index entries for this document
            cur.execute(f"DELETE FROM inverted_index WHERE url = {ph}", (url,))
            cur.close()

            # 4. Build inverted index for title
            self._index_field(conn, url, "title", title_tokens)

            # 5. Build inverted index for content
            self._index_field(conn, url, "content", content_tokens)

            # 6. Update token statistics (incremental)
            self._update_token_stats_incremental(
                conn, title_tokens + content_tokens, old_tokens
            )

            if should_close:
                conn.commit()

        finally:
            if should_close:
                conn.close()

    def update_global_stats(self, conn: Any | None = None) -> None:
        """
        Update global index statistics (total docs, avg doc length).
        Uses pg_class.reltuples for fast approximate counts in PostgreSQL.
        """
        should_close = conn is None
        if conn is None:
            conn = get_connection(self.db_path)

        ph = sql_placeholder()

        try:
            cur = conn.cursor()

            if is_postgres_mode():
                # Fast approximate count via pg_class
                cur.execute(
                    "SELECT reltuples::BIGINT FROM pg_class WHERE relname = 'documents'"
                )
                row = cur.fetchone()
                total_docs = max(int(row[0]), 0) if row else 0

                cur.execute("SELECT AVG(word_count) FROM documents")
                avg_length = cur.fetchone()[0] or 0.0
            else:
                cur.execute("SELECT COUNT(*) FROM documents")
                total_docs = cur.fetchone()[0]

                cur.execute("SELECT AVG(word_count) FROM documents")
                avg_length = cur.fetchone()[0] or 0.0

            # Upsert stats
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

        ph = sql_placeholder()

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
        return [t for t in tokenized.split() if len(t) > 1 and t not in STOP_WORDS]

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

        ph = sql_placeholder()

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
        cur.close()

    def _update_token_stats_incremental(
        self,
        conn: Any,
        tokens: list[str],
        old_tokens: set[str],
    ) -> None:
        """Incrementally update doc_freq: +1 for new tokens, -1 for removed tokens."""
        new_tokens = set(tokens)
        if not new_tokens and not old_tokens:
            return

        ph = sql_placeholder()
        cur = conn.cursor()
        try:
            if is_postgres_mode():
                # Tokens added in this document (need +1)
                added = sorted(new_tokens - old_tokens)
                # Tokens removed from this document (need -1)
                removed = sorted(old_tokens - new_tokens)

                if added:
                    cur.execute(
                        """
                        INSERT INTO token_stats (token, doc_freq)
                        SELECT unnest(%s::text[]), 1
                        ON CONFLICT (token) DO UPDATE SET
                            doc_freq = token_stats.doc_freq + 1
                        """,
                        (added,),
                    )

                if removed:
                    cur.execute(
                        """
                        UPDATE token_stats SET doc_freq = GREATEST(doc_freq - 1, 0)
                        WHERE token = ANY(%s::text[])
                        """,
                        (removed,),
                    )
                return

            # SQLite fallback: full recount per token
            for token in sorted(new_tokens):
                cur.execute(
                    f"SELECT COUNT(DISTINCT url) FROM inverted_index WHERE token = {ph}",
                    (token,),
                )
                doc_freq = cur.fetchone()[0]
                cur.execute(
                    f"""
                    INSERT INTO token_stats (token, doc_freq) VALUES ({ph}, {ph})
                    ON CONFLICT (token) DO UPDATE SET doc_freq = EXCLUDED.doc_freq
                    """,
                    (token, doc_freq),
                )
        finally:
            cur.close()
