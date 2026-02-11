"""
BM25 Scoring Algorithm

Implements the Okapi BM25 ranking function for full-text search.
"""

import math
from dataclasses import dataclass
from typing import Any

from shared.db.search import is_postgres_mode


@dataclass
class BM25Config:
    """BM25 hyperparameters."""

    k1: float = 1.2  # Term frequency saturation
    b: float = 0.75  # Length normalization
    title_boost: float = 3.0  # Boost for title matches
    pagerank_weight: float = 0.5  # Weight for PageRank score (0 to disable)


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


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
        conn: Any,
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
            # Multiplicative: PageRank boosts BM25 score by up to (weight * 100)%
            # e.g. weight=0.5, pagerank=1.0 → 50% boost
            return bm25_score * (1 + self.config.pagerank_weight * pagerank)

        return bm25_score

    def _calculate_bm25(
        self,
        conn: Any,
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

        ph = _placeholder()

        for token in tokens:
            # Get IDF
            idf = self._calculate_idf(conn, token, total_docs)

            # Get term frequencies for this token in this document
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT field, term_freq FROM inverted_index
                WHERE token = {ph} AND url = {ph}
                """,
                (token, url),
            )
            term_data = cur.fetchall()
            cur.close()

            for field, tf in term_data:
                # Apply field boost
                boost = self.config.title_boost if field == "title" else 1.0

                # BM25 term score
                length_norm = 1 - b + b * (doc_length / avg_doc_length)
                tf_saturated = (tf * (k1 + 1)) / (tf + k1 * length_norm)

                score += idf * tf_saturated * boost

        return score

    def _get_pagerank(self, conn: Any, url: str) -> float:
        """Get PageRank score for a URL (0.0 if not found)."""
        ph = _placeholder()
        cur = conn.cursor()
        cur.execute(
            f"SELECT score FROM page_ranks WHERE url = {ph}",
            (url,),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else 0.0

    def _get_global_stats(
        self,
        conn: Any,
    ) -> tuple[float, float]:
        """Get total docs and average doc length (cached)."""
        if "total_docs" not in self._stats_cache:
            cur = conn.cursor()
            cur.execute(
                "SELECT key, value FROM index_stats WHERE key IN ('total_docs', 'avg_doc_length')"
            )
            rows = cur.fetchall()
            cur.close()

            stats = {k: v for k, v in rows}
            self._stats_cache["total_docs"] = stats.get("total_docs", 0)
            self._stats_cache["avg_doc_length"] = stats.get("avg_doc_length", 0)

        return self._stats_cache["total_docs"], self._stats_cache["avg_doc_length"]

    def _get_doc_length(self, conn: Any, url: str) -> int:
        """Get document word count."""
        ph = _placeholder()
        cur = conn.cursor()
        cur.execute(
            f"SELECT word_count FROM documents WHERE url = {ph}",
            (url,),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else 0

    def _calculate_idf(
        self,
        conn: Any,
        token: str,
        total_docs: float,
    ) -> float:
        """
        Calculate Inverse Document Frequency.

        IDF = log((N - df + 0.5) / (df + 0.5) + 1)

        Using the "+1" variant to avoid negative IDF for common terms.
        """
        # Get document frequency
        ph = _placeholder()
        cur = conn.cursor()
        cur.execute(
            f"SELECT doc_freq FROM token_stats WHERE token = {ph}",
            (token,),
        )
        row = cur.fetchone()
        cur.close()

        df = row[0] if row else 0

        if df == 0:
            return 0.0

        # IDF formula (BM25 variant with +1 to avoid negative values)
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

        return idf

    def score_batch(
        self,
        conn: Any,
        candidates: list[str],
        tokens: list[str],
    ) -> list[tuple[str, float]]:
        """Score all candidates in batch with minimal DB queries."""
        if not candidates or not tokens:
            return []

        total_docs, avg_doc_length = self._get_global_stats(conn)
        if total_docs == 0 or avg_doc_length == 0:
            return [(url, 0.0) for url in candidates]

        ph = _placeholder()
        url_list = candidates
        token_phs = ",".join([ph] * len(tokens))
        url_phs = ",".join([ph] * len(url_list))

        cur = conn.cursor()

        # Batch 1: token_stats (IDF values)
        cur.execute(
            f"SELECT token, doc_freq FROM token_stats WHERE token IN ({token_phs})",
            tuple(tokens),
        )
        idf_map: dict[str, float] = {}
        for token, df in cur.fetchall():
            if df > 0:
                idf_map[token] = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

        # Batch 2: inverted_index entries for all (token, url) combinations
        cur.execute(
            f"""
            SELECT url, token, field, term_freq FROM inverted_index
            WHERE token IN ({token_phs}) AND url IN ({url_phs})
            """,
            (*tokens, *url_list),
        )
        # {(url, token): [(field, tf), ...]}
        inv_map: dict[tuple[str, str], list[tuple[str, int]]] = {}
        for url, token, field, tf in cur.fetchall():
            inv_map.setdefault((url, token), []).append((field, tf))

        # Batch 3: word_count for all candidate URLs
        cur.execute(
            f"SELECT url, word_count FROM documents WHERE url IN ({url_phs})",
            tuple(url_list),
        )
        wc_map: dict[str, int] = {url: wc for url, wc in cur.fetchall()}

        # Batch 4: page_ranks for all candidate URLs
        pr_map: dict[str, float] = {}
        if self.config.pagerank_weight > 0:
            cur.execute(
                f"SELECT url, score FROM page_ranks WHERE url IN ({url_phs})",
                tuple(url_list),
            )
            pr_map = {url: score for url, score in cur.fetchall()}

        cur.close()

        # Compute BM25 scores in-memory
        k1 = self.config.k1
        b = self.config.b
        results: list[tuple[str, float]] = []

        for url in url_list:
            doc_length = wc_map.get(url, 1) or 1
            bm25_score = 0.0

            for token in tokens:
                idf = idf_map.get(token, 0.0)
                if idf == 0.0:
                    continue

                entries = inv_map.get((url, token), [])
                for field, tf in entries:
                    boost = self.config.title_boost if field == "title" else 1.0
                    length_norm = 1 - b + b * (doc_length / avg_doc_length)
                    tf_saturated = (tf * (k1 + 1)) / (tf + k1 * length_norm)
                    bm25_score += idf * tf_saturated * boost

            # Apply PageRank boost
            if self.config.pagerank_weight > 0:
                pagerank = pr_map.get(url, 0.0)
                bm25_score *= 1 + self.config.pagerank_weight * pagerank

            results.append((url, bm25_score))

        return results

    def clear_cache(self) -> None:
        """Clear the stats cache."""
        self._stats_cache.clear()
