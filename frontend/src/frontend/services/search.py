import sqlite3
import os
import numpy as np
from typing import Any
from frontend.core.config import settings
from frontend.services.embedding import embedding_service

SEARCH_SQL = """
SELECT
  p.url,
  COALESCE(p.raw_title, p.title) as title,
  COALESCE(p.raw_content, p.content) as content,
  bm25(p.pages, 0.0, 3.0, 1.0) - (COALESCE(r.score, 0) * ?) AS rank
FROM pages p
LEFT JOIN page_ranks r ON p.url = r.url
WHERE p.pages MATCH ?
ORDER BY rank
LIMIT ? OFFSET ?;
"""

COUNT_SQL = "SELECT count(*) FROM pages WHERE pages MATCH ?;"


class SearchService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self._vector_cache = None  # Cache for vectors (list of (url, vector))
        self._last_cache_update = 0.0
        self.CACHE_TTL = 60.0  # Refresh cache every 60 seconds

    def search(
        self,
        q: str | None,
        k: int = 10,
        page: int = 1,
        pr_weight: float = 1000.0,
        mode: str = "default",
    ) -> dict[str, Any]:
        """
        Search with support for Semantic Search (mode='semantic') and Hybrid (mode='hybrid').

        Modes:
        - 'default': FTS (BM25) search
        - 'semantic': Vector similarity search
        - 'hybrid': Combined FTS + Semantic using Reciprocal Rank Fusion
        """
        if not q:
            return self._empty_result(k)

        if mode == "semantic":
            return self.vector_search(q, k, page)

        if mode == "hybrid":
            return self.hybrid_search(q, k, page, pr_weight)

        page = max(int(page), 1)
        offset = (page - 1) * k

        # Tokenize query for FTS5 (unicode61)
        # If we didn't tokenize, "今日は" would be one token and fail to match "今日 は".
        from frontend.indexer.analyzer import analyzer

        analyzed_q = analyzer.tokenize(q)

        # Fallback if empty (e.g. only symbols)
        if not analyzed_q.strip():
            analyzed_q = q

        con = sqlite3.connect(self.db_path)
        try:
            try:
                # Parameters: pr_weight, query, limit, offset
                total = con.execute(COUNT_SQL, (analyzed_q,)).fetchone()[0]
                rows = con.execute(
                    SEARCH_SQL, (pr_weight, analyzed_q, k, offset)
                ).fetchall()
            except sqlite3.OperationalError:
                return self._empty_result(k, q=q)

            # Generate Snippets in Python
            from frontend.services.text_utils import highlight_snippet

            search_terms = (
                analyzed_q.split()
            )  # Analyzed query is space-separated tokens

            hits = []
            for u, t, content, r in rows:
                hits.append(
                    {
                        "url": u,
                        "title": t,
                        "snip": highlight_snippet(content, search_terms),
                        "rank": r,
                    }
                )
            last_page = max((total + k - 1) // k, 1)
            return {
                "query": q,
                "total": total,
                "page": page,
                "per_page": k,
                "last_page": last_page,
                "hits": hits,
            }
        finally:
            con.close()

    def vector_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        """
        Perform brute-force vector search.
        """
        # 1. Embed Query
        query_vec = embedding_service.embed_query(q)

        # 2. Load Candidates (Caching for performance)
        import time

        if self._vector_cache is None or (
            time.time() - self._last_cache_update > self.CACHE_TTL
        ):
            self._load_vector_cache()

        if not self._vector_cache:
            return self._empty_result(k, q=q)

        # 3. Compute Similarity (Dot Product if normalized, or Cosine)
        # Assuming model outputs normalized vectors? sentence-transformers usually does.
        # But let's compute cosine: dot(a, b) / (norm(a)*norm(b))

        urls = [item[0] for item in self._vector_cache]
        vectors = np.array([item[1] for item in self._vector_cache])  # Shape (N, D)

        # Compute cosine similarity
        norm_q = np.linalg.norm(query_vec)
        norm_docs = np.linalg.norm(vectors, axis=1)

        # Avoid zero division
        dots = np.dot(vectors, query_vec)
        sims = dots / (norm_docs * norm_q + 1e-9)

        # 4. Sort
        top_indices = np.argsort(sims)[::-1]  # Descending

        # Pagination
        start = (page - 1) * k
        end = start + k

        total = len(urls)
        slice_indices = top_indices[start:end]

        # Fetch details for hits (Title, Snippet) from DB
        hits = []
        con = sqlite3.connect(self.db_path)
        try:
            for idx in slice_indices:
                url = urls[idx]
                score = float(sims[idx])
                # Fetch metadata (prefer raw_title/raw_content)
                row = con.execute(
                    """
                    SELECT
                        COALESCE(raw_title, title),
                        COALESCE(raw_content, content)
                    FROM pages WHERE url = ?
                """,
                    (url,),
                ).fetchone()
                if row:
                    title, content = row

                    # Generate Snippet
                    from frontend.services.text_utils import highlight_snippet

                    # For vector search, we should highlight the original query terms?
                    # Or analyze them? Let's analyze them to match what likely matched.
                    from frontend.indexer.analyzer import analyzer

                    analyzed_q_vec = analyzer.tokenize(q)
                    search_terms_vec = analyzed_q_vec.split()

                    snip = highlight_snippet(content, search_terms_vec)

                    hits.append(
                        {
                            "url": url,
                            "title": title,
                            "snip": snip,
                            "rank": score,  # Similarity score (0.0 - 1.0)
                        }
                    )
        finally:
            con.close()

        last_page = max((total + k - 1) // k, 1)
        return {
            "query": q,
            "total": total,
            "page": page,
            "per_page": k,
            "last_page": last_page,
            "hits": hits,
        }

    def hybrid_search(
        self, q: str, k: int = 10, page: int = 1, pr_weight: float = 1000.0
    ) -> dict[str, Any]:
        """
        Hybrid search combining FTS (BM25) and Semantic (Vector) results.
        Uses Reciprocal Rank Fusion (RRF) for score combination.

        RRF formula: score = sum(1 / (rrf_k + rank)) for each result list
        where rrf_k is typically 60 (constant to prevent high-ranked results dominating)
        """
        RRF_K = 60  # Standard RRF constant

        # Get more results from each method for better fusion
        fetch_k = k * 3  # Fetch 3x to ensure enough overlap

        # 1. Get FTS results (default mode)
        fts_result = self.search(
            q, k=fetch_k, page=1, pr_weight=pr_weight, mode="default"
        )
        fts_hits = fts_result.get("hits", [])

        # 2. Get Semantic results
        semantic_result = self.vector_search(q, k=fetch_k, page=1)
        semantic_hits = semantic_result.get("hits", [])

        # 3. Build RRF scores
        rrf_scores: dict[str, float] = {}
        url_data: dict[str, dict] = {}  # Store title, snip for each URL

        # Add FTS contributions
        for rank, hit in enumerate(fts_hits, start=1):
            url = hit["url"]
            rrf_scores[url] = rrf_scores.get(url, 0) + 1.0 / (RRF_K + rank)
            if url not in url_data:
                url_data[url] = {"title": hit["title"], "snip": hit["snip"]}

        # Add Semantic contributions
        for rank, hit in enumerate(semantic_hits, start=1):
            url = hit["url"]
            rrf_scores[url] = rrf_scores.get(url, 0) + 1.0 / (RRF_K + rank)
            if url not in url_data:
                url_data[url] = {"title": hit["title"], "snip": hit["snip"]}

        # 4. Sort by RRF score (higher is better)
        sorted_urls = sorted(
            rrf_scores.keys(), key=lambda u: rrf_scores[u], reverse=True
        )

        # 5. Paginate
        total = len(sorted_urls)
        start = (page - 1) * k
        end = start + k
        page_urls = sorted_urls[start:end]

        # 6. Build final hits
        hits = []
        for url in page_urls:
            data = url_data[url]
            hits.append(
                {
                    "url": url,
                    "title": data["title"],
                    "snip": data["snip"],
                    "rank": rrf_scores[url],  # RRF score
                }
            )

        last_page = max((total + k - 1) // k, 1)
        return {
            "query": q,
            "total": total,
            "page": page,
            "per_page": k,
            "last_page": last_page,
            "hits": hits,
        }

    def _load_vector_cache(self):
        """Load all embeddings from DB into memory."""
        import time

        self._last_cache_update = time.time()

        if not os.path.exists(self.db_path):
            self._vector_cache = []
            return

        con = sqlite3.connect(self.db_path)
        try:
            # Check table
            try:
                con.execute("SELECT count(*) FROM page_embeddings")
            except sqlite3.OperationalError:
                self._vector_cache = []
                return

            rows = con.execute("SELECT url, embedding FROM page_embeddings").fetchall()
            cache = []
            for url, blob in rows:
                vec = embedding_service.deserialize(blob)
                cache.append((url, vec))
            self._vector_cache = cache
        finally:
            con.close()

    def get_index_stats(self) -> dict[str, int]:
        """Return index stats: total pages."""
        if not os.path.exists(self.db_path):
            return {"indexed": 0}

        con = sqlite3.connect(self.db_path)
        try:
            cur = con.execute("SELECT count(*) FROM pages")
            count = cur.fetchone()[0]
            return {"indexed": count}
        except sqlite3.OperationalError:
            return {"indexed": 0}
        finally:
            con.close()

    def _empty_result(self, k: int, q: str = "") -> dict[str, Any]:
        return {
            "query": q,
            "total": 0,
            "page": 1,
            "per_page": k,
            "last_page": 1,
            "hits": [],
        }


# Global instance
search_service = SearchService()
