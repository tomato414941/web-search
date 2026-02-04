"""
Custom Full-Text Search Engine

Provides search functionality using the inverted index.
Supports BM25, Vector (Semantic), and Hybrid (RRF) search modes.
"""

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from shared.analyzer import analyzer
from shared.db.search import get_connection, is_postgres_mode
from shared.search.scoring import BM25Scorer, BM25Config


# Type alias for embedding function
EmbeddingFunc = Callable[[str], np.ndarray]


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


@dataclass
class SearchHit:
    """A single search result."""

    url: str
    title: str
    content: str
    score: float


@dataclass
class SearchResult:
    """Search results with metadata."""

    query: str
    total: int
    hits: list[SearchHit]
    page: int
    per_page: int
    last_page: int


class SearchEngine:
    """
    Custom full-text search engine using inverted index.

    Supports multiple search modes:
    - BM25 (default): Traditional keyword search with BM25 ranking
    - Vector: Semantic search using embeddings
    - Hybrid: Combines BM25 and Vector using Reciprocal Rank Fusion (RRF)
    """

    RRF_K = 60  # Standard RRF constant

    def __init__(
        self,
        db_path: str,
        bm25_config: BM25Config | None = None,
        embed_query_func: EmbeddingFunc | None = None,
        deserialize_func: Callable[[bytes], np.ndarray] | None = None,
    ):
        """
        Initialize search engine.

        Args:
            db_path: Path to SQLite database
            bm25_config: BM25 configuration
            embed_query_func: Function to embed query text (required for vector/hybrid search)
            deserialize_func: Function to deserialize embedding blobs from DB
        """
        self.db_path = db_path
        self.scorer = BM25Scorer(db_path, bm25_config)
        self._embed_query = embed_query_func
        self._deserialize = deserialize_func
        self._vector_cache: list[tuple[str, np.ndarray]] | None = None

    def search(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
    ) -> SearchResult:
        """
        Search documents using AND logic.

        Args:
            query: Search query string
            limit: Number of results per page
            page: Page number (1-indexed)

        Returns:
            SearchResult with matching documents
        """
        if not query or not query.strip():
            return self._empty_result(query, limit)

        # 1. Tokenize query
        tokens = self._tokenize(query)
        if not tokens:
            return self._empty_result(query, limit)

        conn = get_connection(self.db_path)
        try:
            # 2. Find candidate documents (AND logic)
            candidates = self._find_candidates(conn, tokens)
            if not candidates:
                return self._empty_result(query, limit)

            # 3. Score candidates (basic term frequency for now)
            scored = self._score_candidates(conn, candidates, tokens)

            # 4. Sort by score (descending)
            scored.sort(key=lambda x: x[1], reverse=True)

            # 5. Paginate
            total = len(scored)
            offset = (page - 1) * limit
            page_results = scored[offset : offset + limit]

            # 6. Fetch document details
            hits = []
            ph = _placeholder()
            for url, score in page_results:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT title, content FROM documents WHERE url = {ph}",
                    (url,),
                )
                doc = cur.fetchone()
                cur.close()
                if doc:
                    hits.append(
                        SearchHit(
                            url=url,
                            title=doc[0],
                            content=doc[1],
                            score=score,
                        )
                    )

            last_page = max((total + limit - 1) // limit, 1)

            return SearchResult(
                query=query,
                total=total,
                hits=hits,
                page=page,
                per_page=limit,
                last_page=last_page,
            )

        finally:
            conn.close()

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text using SudachiPy analyzer."""
        if not text:
            return []
        tokenized = analyzer.tokenize(text)
        return tokenized.split()

    def _find_candidates(
        self,
        conn: Any,
        tokens: list[str],
    ) -> set[str]:
        """
        Find documents containing ALL tokens (AND logic).
        """
        if not tokens:
            return set()

        ph = _placeholder()

        # Get documents for first token
        cur = conn.cursor()
        cur.execute(
            f"SELECT DISTINCT url FROM inverted_index WHERE token = {ph}",
            (tokens[0],),
        )
        candidates = set(row[0] for row in cur.fetchall())
        cur.close()

        # Intersect with remaining tokens
        for token in tokens[1:]:
            cur = conn.cursor()
            cur.execute(
                f"SELECT DISTINCT url FROM inverted_index WHERE token = {ph}",
                (token,),
            )
            token_docs = set(row[0] for row in cur.fetchall())
            cur.close()
            candidates &= token_docs

            # Early exit if no candidates
            if not candidates:
                return set()

        return candidates

    def _score_candidates(
        self,
        conn: Any,
        candidates: set[str],
        tokens: list[str],
    ) -> list[tuple[str, float]]:
        """Score candidates using BM25 algorithm."""
        scored = []

        for url in candidates:
            score = self.scorer.score(conn, url, tokens)
            scored.append((url, score))

        return scored

    def vector_search(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
    ) -> SearchResult:
        """
        Semantic search using vector embeddings.

        Requires embed_query_func and deserialize_func to be set.

        Args:
            query: Search query string
            limit: Number of results per page
            page: Page number (1-indexed)

        Returns:
            SearchResult with semantically similar documents
        """
        if not query or not query.strip():
            return self._empty_result(query, limit)

        if self._embed_query is None or self._deserialize is None:
            return self._empty_result(query, limit)

        # 1. Embed query
        query_vec = self._embed_query(query)

        # 2. Load vector cache
        self._load_vector_cache()

        if not self._vector_cache:
            return self._empty_result(query, limit)

        # 3. Compute cosine similarity
        urls = [item[0] for item in self._vector_cache]
        vectors = np.array([item[1] for item in self._vector_cache])

        norm_q = np.linalg.norm(query_vec)
        norm_docs = np.linalg.norm(vectors, axis=1)
        dots = np.dot(vectors, query_vec)
        sims = dots / (norm_docs * norm_q + 1e-9)

        # 4. Sort by similarity (descending)
        top_indices = np.argsort(sims)[::-1]

        # 5. Paginate
        total = len(urls)
        start = (page - 1) * limit
        end = start + limit
        slice_indices = top_indices[start:end]

        # 6. Fetch document details
        hits = []
        conn = get_connection(self.db_path)
        ph = _placeholder()
        try:
            for idx in slice_indices:
                url = urls[idx]
                score = float(sims[idx])

                cur = conn.cursor()
                cur.execute(
                    f"SELECT title, content FROM documents WHERE url = {ph}",
                    (url,),
                )
                doc = cur.fetchone()
                cur.close()

                if doc:
                    hits.append(
                        SearchHit(
                            url=url,
                            title=doc[0],
                            content=doc[1],
                            score=score,
                        )
                    )
        finally:
            conn.close()

        last_page = max((total + limit - 1) // limit, 1)

        return SearchResult(
            query=query,
            total=total,
            hits=hits,
            page=page,
            per_page=limit,
            last_page=last_page,
        )

    def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
    ) -> SearchResult:
        """
        Hybrid search combining BM25 and Vector using Reciprocal Rank Fusion.

        RRF formula: score = sum(1 / (rrf_k + rank)) for each result list

        Args:
            query: Search query string
            limit: Number of results per page
            page: Page number (1-indexed)

        Returns:
            SearchResult with hybrid-ranked documents
        """
        if not query or not query.strip():
            return self._empty_result(query, limit)

        # Fetch more results from each method for better fusion
        fetch_k = limit * 3

        # 1. Get BM25 results
        bm25_result = self.search(query, limit=fetch_k, page=1)
        bm25_hits = bm25_result.hits

        # 2. Get Vector results (if available)
        vector_hits: list[SearchHit] = []
        if self._embed_query is not None and self._deserialize is not None:
            vector_result = self.vector_search(query, limit=fetch_k, page=1)
            vector_hits = vector_result.hits

        # 3. Build RRF scores
        rrf_scores: dict[str, float] = {}
        url_data: dict[str, SearchHit] = {}

        # Add BM25 contributions
        for rank, hit in enumerate(bm25_hits, start=1):
            rrf_scores[hit.url] = rrf_scores.get(hit.url, 0) + 1.0 / (self.RRF_K + rank)
            if hit.url not in url_data:
                url_data[hit.url] = hit

        # Add Vector contributions
        for rank, hit in enumerate(vector_hits, start=1):
            rrf_scores[hit.url] = rrf_scores.get(hit.url, 0) + 1.0 / (self.RRF_K + rank)
            if hit.url not in url_data:
                url_data[hit.url] = hit

        # 4. Sort by RRF score (higher is better)
        sorted_urls = sorted(
            rrf_scores.keys(),
            key=lambda u: rrf_scores[u],
            reverse=True,
        )

        # 5. Paginate
        total = len(sorted_urls)
        start = (page - 1) * limit
        end = start + limit
        page_urls = sorted_urls[start:end]

        # 6. Build final hits
        hits = []
        for url in page_urls:
            original = url_data[url]
            hits.append(
                SearchHit(
                    url=url,
                    title=original.title,
                    content=original.content,
                    score=rrf_scores[url],
                )
            )

        last_page = max((total + limit - 1) // limit, 1)

        return SearchResult(
            query=query,
            total=total,
            hits=hits,
            page=page,
            per_page=limit,
            last_page=last_page,
        )

    def _load_vector_cache(self) -> None:
        """Load all embeddings from DB into memory."""
        if self._vector_cache is not None:
            return  # Already loaded

        if self._deserialize is None:
            self._vector_cache = []
            return

        conn = get_connection(self.db_path)
        try:
            # Check if table exists
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM page_embeddings")
                cur.close()
            except Exception:
                self._vector_cache = []
                return

            cur = conn.cursor()
            cur.execute("SELECT url, embedding FROM page_embeddings")
            rows = cur.fetchall()
            cur.close()

            cache = []
            for url, blob in rows:
                # Handle PostgreSQL memoryview
                if isinstance(blob, memoryview):
                    blob = bytes(blob)
                vec = self._deserialize(blob)
                cache.append((url, vec))

            self._vector_cache = cache

        finally:
            conn.close()

    def clear_vector_cache(self) -> None:
        """Clear the vector cache (call after indexing new documents)."""
        self._vector_cache = None

    def _empty_result(self, query: str, limit: int) -> SearchResult:
        """Return empty search result."""
        return SearchResult(
            query=query,
            total=0,
            hits=[],
            page=1,
            per_page=limit,
            last_page=1,
        )
