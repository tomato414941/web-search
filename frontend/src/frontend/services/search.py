"""
Search Service - Frontend search functionality using custom search engine.

Uses BM25 keyword search with PageRank boosting.
Vector/hybrid search is disabled until index scale justifies the latency cost.
"""

from typing import Any

from frontend.core.config import settings
from shared.db.search import get_connection
from shared.search import SearchEngine, BM25Config
from shared.search.snippet import generate_snippet
from shared.analyzer import analyzer


class SearchService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

        self._engine = SearchEngine(
            db_path=db_path,
            bm25_config=BM25Config(
                k1=1.2,
                b=0.75,
                title_boost=3.0,
                pagerank_weight=0.5,
            ),
        )

    def search(
        self,
        q: str | None,
        k: int = 10,
        page: int = 1,
    ) -> dict[str, Any]:
        if not q:
            return self._empty_result(k)

        return self._bm25_search(q, k, page)

    def _bm25_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        result = self._engine.search(q, limit=k, page=page)

        # Tokenize for snippet highlighting
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
