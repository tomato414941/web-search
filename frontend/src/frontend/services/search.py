"""
Search Service - Frontend search functionality.

Supports BM25, vector (semantic), and hybrid (BM25 + vector RRF) search modes.
Default mode is hybrid when embeddings are available, otherwise BM25.
"""

import logging
import os
import time
from typing import Any

from frontend.api.metrics import (
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
)
from frontend.core.config import settings
from frontend.services.embedding import deserialize_func, embed_query_func
from shared.analyzer import analyzer
from shared.db.search import get_connection
from shared.search import BM25Config, SearchEngine
from shared.search.snippet import generate_snippet

logger = logging.getLogger(__name__)


def _bm25_config_from_env() -> BM25Config:
    return BM25Config(
        k1=float(os.getenv("BM25_K1", "1.2")),
        b=float(os.getenv("BM25_B", "0.75")),
        title_boost=float(os.getenv("BM25_TITLE_BOOST", "3.0")),
        pagerank_weight=float(os.getenv("BM25_PAGERANK_WEIGHT", "0.5")),
    )


class SearchService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

        self._engine = SearchEngine(
            db_path=db_path,
            bm25_config=_bm25_config_from_env(),
            embed_query_func=embed_query_func,
            deserialize_func=deserialize_func,
        )

    @property
    def hybrid_available(self) -> bool:
        return self._engine._embed_query is not None

    def search(
        self,
        q: str | None,
        k: int = 10,
        page: int = 1,
        mode: str = "auto",
    ) -> dict[str, Any]:
        if not q:
            return self._empty_result(k)

        if mode == "hybrid" and self.hybrid_available:
            return self._hybrid_search(q, k, page)
        elif mode == "semantic" and self.hybrid_available:
            return self._vector_search(q, k, page)
        elif mode == "auto" and self.hybrid_available:
            return self._hybrid_search(q, k, page)
        else:
            return self._bm25_search(q, k, page)

    def _bm25_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="bm25").inc()
        t0 = time.monotonic()
        result = self._engine.search(q, limit=k, page=page)
        SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
        SEARCH_RESULT_COUNT.observe(result.total)
        return self._format_result(q, result)

    def _hybrid_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="hybrid").inc()
        t0 = time.monotonic()
        try:
            result = self._engine.hybrid_search(q, limit=k, page=page)
        except Exception:
            logger.warning("Hybrid search failed, falling back to BM25", exc_info=True)
            result = self._engine.search(q, limit=k, page=page)
        SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
        SEARCH_RESULT_COUNT.observe(result.total)
        return self._format_result(q, result)

    def _vector_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="semantic").inc()
        t0 = time.monotonic()
        try:
            result = self._engine.vector_search(q, limit=k, page=page)
        except Exception:
            logger.warning("Vector search failed, falling back to BM25", exc_info=True)
            result = self._engine.search(q, limit=k, page=page)
        SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
        SEARCH_RESULT_COUNT.observe(result.total)
        return self._format_result(q, result)

    def _format_result(self, q: str, result: Any) -> dict[str, Any]:
        analyzed_q = analyzer.tokenize(q)
        search_terms = analyzed_q.split() if analyzed_q.strip() else [q]

        hits = []
        for hit in result.hits:
            snippet = generate_snippet(hit.content, search_terms)
            hits.append(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "snip": snippet.text,
                    "snip_plain": snippet.plain_text,
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

    def get_index_stats(self) -> dict[str, int]:
        """Return index stats: total pages."""
        try:
            con = get_connection(self.db_path)
            cur = con.cursor()
            cur.execute("SELECT count(*) FROM documents")
            count = cur.fetchone()[0]
            cur.close()
            con.close()
            return {"indexed": count}
        except Exception:
            return {"indexed": 0}

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
