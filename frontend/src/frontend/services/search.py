"""
Search Service - Frontend search functionality using custom search engine.

Supports three search modes:
- default: BM25 keyword search
- semantic: Vector similarity search
- hybrid: Combined BM25 + Semantic using RRF
"""

import os
import sqlite3
from typing import Any

from frontend.core.config import settings
from frontend.core.db import get_connection
from frontend.services.embedding import embedding_service
from shared.search import SearchEngine, BM25Config
from shared.search.snippet import highlight_snippet
from shared.analyzer import analyzer


class SearchService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

        # Initialize search engine with embedding support
        self._engine = SearchEngine(
            db_path=db_path,
            bm25_config=BM25Config(
                k1=1.2,
                b=0.75,
                title_boost=3.0,
                pagerank_weight=0.5,
            ),
            embed_query_func=self._embed_query,
            deserialize_func=embedding_service.deserialize,
        )

    def _embed_query(self, text: str):
        """Embed query text using the embedding service."""
        return embedding_service.embed_query(text)

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
        - 'default': BM25 search with PageRank
        - 'semantic': Vector similarity search
        - 'hybrid': Combined BM25 + Semantic using Reciprocal Rank Fusion
        """
        if not q:
            return self._empty_result(k)

        if mode == "semantic":
            return self._vector_search(q, k, page)

        if mode == "hybrid":
            return self._hybrid_search(q, k, page)

        # Default: BM25 search
        page = max(int(page), 1)

        result = self._engine.search(q, limit=k, page=page)

        # Tokenize for snippet highlighting
        analyzed_q = analyzer.tokenize(q)
        search_terms = analyzed_q.split() if analyzed_q.strip() else [q]

        hits = []
        for hit in result.hits:
            hits.append(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "snip": highlight_snippet(hit.content, search_terms),
                    "rank": hit.score,
                }
            )

        return {
            "query": q,
            "total": result.total,
            "page": page,  # Return requested page, not result page
            "per_page": result.per_page,
            "last_page": result.last_page,
            "hits": hits,
        }

    def _vector_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        """Perform semantic vector search."""
        result = self._engine.vector_search(q, limit=k, page=page)

        # Tokenize for snippet highlighting
        analyzed_q = analyzer.tokenize(q)
        search_terms = analyzed_q.split() if analyzed_q.strip() else [q]

        hits = []
        for hit in result.hits:
            hits.append(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "snip": highlight_snippet(hit.content, search_terms),
                    "rank": hit.score,
                }
            )

        return {
            "query": q,
            "total": result.total,
            "page": result.page,
            "per_page": result.per_page,
            "last_page": result.last_page,
            "hits": hits,
        }

    def _hybrid_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        """Perform hybrid BM25 + vector search using RRF."""
        result = self._engine.hybrid_search(q, limit=k, page=page)

        # Tokenize for snippet highlighting
        analyzed_q = analyzer.tokenize(q)
        search_terms = analyzed_q.split() if analyzed_q.strip() else [q]

        hits = []
        for hit in result.hits:
            hits.append(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "snip": highlight_snippet(hit.content, search_terms),
                    "rank": hit.score,
                }
            )

        return {
            "query": q,
            "total": result.total,
            "page": result.page,
            "per_page": result.per_page,
            "last_page": result.last_page,
            "hits": hits,
        }

    # Backward compatibility aliases
    def vector_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        """Alias for _vector_search (backward compatibility)."""
        return self._vector_search(q, k, page)

    def hybrid_search(
        self, q: str, k: int = 10, page: int = 1, pr_weight: float = 1000.0
    ) -> dict[str, Any]:
        """Alias for _hybrid_search (backward compatibility)."""
        return self._hybrid_search(q, k, page)

    def get_index_stats(self) -> dict[str, int]:
        """Return index stats: total pages."""
        if not os.path.exists(self.db_path):
            return {"indexed": 0}

        con = get_connection(self.db_path)
        try:
            # Use new documents table
            cur = con.execute("SELECT count(*) FROM documents")
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
