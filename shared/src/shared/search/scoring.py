"""
BM25 Scoring Algorithm

Implements the Okapi BM25 ranking function for full-text search.
"""

import math
import sqlite3
from dataclasses import dataclass


@dataclass
class BM25Config:
    """BM25 hyperparameters."""

    k1: float = 1.2  # Term frequency saturation
    b: float = 0.75  # Length normalization
    title_boost: float = 3.0  # Boost for title matches
    pagerank_weight: float = 0.5  # Weight for PageRank score (0 to disable)


class BM25Scorer:
    """
    BM25 scoring implementation.

    BM25 formula:
    score(q, d) = Σ IDF(t) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * |d| / avgdl))

    Where:
    - IDF(t) = log((N - df + 0.5) / (df + 0.5) + 1)
    - N = total number of documents
    - df = document frequency (how many docs contain the term)
    - tf = term frequency in document
    - |d| = document length (word count)
    - avgdl = average document length
    """

    def __init__(self, db_path: str, config: BM25Config | None = None):
        self.db_path = db_path
        self.config = config or BM25Config()
        self._stats_cache: dict[str, float] = {}

    def score(
        self,
        conn: sqlite3.Connection,
        url: str,
        tokens: list[str],
    ) -> float:
        """
        Calculate combined BM25 + PageRank score for a document.

        Args:
            conn: Database connection
            url: Document URL
            tokens: Query tokens

        Returns:
            Combined score (higher is better)
        """
        bm25_score = self._calculate_bm25(conn, url, tokens)

        # Add PageRank contribution if enabled
        if self.config.pagerank_weight > 0:
            pagerank = self._get_pagerank(conn, url)
            # Combine: BM25 + (PageRank * weight)
            # PageRank is typically 0-1, so weight controls its influence
            return bm25_score + (pagerank * self.config.pagerank_weight)

        return bm25_score

    def _calculate_bm25(
        self,
        conn: sqlite3.Connection,
        url: str,
        tokens: list[str],
    ) -> float:
        """Calculate pure BM25 score."""
        # Load global stats (cached)
        total_docs, avg_doc_length = self._get_global_stats(conn)

        if total_docs == 0 or avg_doc_length == 0:
            return 0.0

        # Get document length
        doc_length = self._get_doc_length(conn, url)
        if doc_length == 0:
            doc_length = 1  # Avoid division by zero

        score = 0.0
        k1 = self.config.k1
        b = self.config.b

        for token in tokens:
            # Get IDF
            idf = self._calculate_idf(conn, token, total_docs)

            # Get term frequencies for this token in this document
            term_data = conn.execute(
                """
                SELECT field, term_freq FROM inverted_index
                WHERE token = ? AND url = ?
                """,
                (token, url),
            ).fetchall()

            for field, tf in term_data:
                # Apply field boost
                boost = self.config.title_boost if field == "title" else 1.0

                # BM25 term score
                length_norm = 1 - b + b * (doc_length / avg_doc_length)
                tf_saturated = (tf * (k1 + 1)) / (tf + k1 * length_norm)

                score += idf * tf_saturated * boost

        return score

    def _get_pagerank(self, conn: sqlite3.Connection, url: str) -> float:
        """Get PageRank score for a URL (0.0 if not found)."""
        row = conn.execute(
            "SELECT score FROM page_ranks WHERE url = ?",
            (url,),
        ).fetchone()
        return row[0] if row else 0.0

    def _get_global_stats(
        self,
        conn: sqlite3.Connection,
    ) -> tuple[float, float]:
        """Get total docs and average doc length (cached)."""
        if "total_docs" not in self._stats_cache:
            row = conn.execute(
                "SELECT key, value FROM index_stats WHERE key IN ('total_docs', 'avg_doc_length')"
            ).fetchall()

            stats = {k: v for k, v in row}
            self._stats_cache["total_docs"] = stats.get("total_docs", 0)
            self._stats_cache["avg_doc_length"] = stats.get("avg_doc_length", 0)

        return self._stats_cache["total_docs"], self._stats_cache["avg_doc_length"]

    def _get_doc_length(self, conn: sqlite3.Connection, url: str) -> int:
        """Get document word count."""
        row = conn.execute(
            "SELECT word_count FROM documents WHERE url = ?",
            (url,),
        ).fetchone()
        return row[0] if row else 0

    def _calculate_idf(
        self,
        conn: sqlite3.Connection,
        token: str,
        total_docs: float,
    ) -> float:
        """
        Calculate Inverse Document Frequency.

        IDF = log((N - df + 0.5) / (df + 0.5) + 1)

        Using the "+1" variant to avoid negative IDF for common terms.
        """
        # Get document frequency
        row = conn.execute(
            "SELECT doc_freq FROM token_stats WHERE token = ?",
            (token,),
        ).fetchone()

        df = row[0] if row else 0

        if df == 0:
            return 0.0

        # IDF formula (BM25 variant with +1 to avoid negative values)
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

        return idf

    def clear_cache(self) -> None:
        """Clear the stats cache."""
        self._stats_cache.clear()
