"""
Search Service - Frontend search functionality.

Supports BM25 (OpenSearch), vector (pgvector), and hybrid (OpenSearch BM25 + k-NN) modes.
Default (auto) mode uses BM25 for speed; hybrid/semantic available via explicit mode.
"""

import concurrent.futures
import logging
import time
from typing import Any

from frontend.api.metrics import (
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
)
from frontend.core.config import settings
from frontend.services.embedding import embed_query_func
from shared.search_kernel.analyzer import analyzer
from shared.contracts.enums import SearchMode
from shared.search_kernel.snippet import generate_snippet

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self._embed_query = embed_query_func
        self._os_client = None
        self._os_enabled = settings.OPENSEARCH_ENABLED
        if self._os_enabled:
            self._init_opensearch()

    def _init_opensearch(self) -> None:
        try:
            from shared.opensearch.client import get_client
            from shared.opensearch.mapping import ensure_index

            self._os_client = get_client(settings.OPENSEARCH_URL)
            ensure_index(self._os_client)
            logger.info("OpenSearch search enabled: %s", settings.OPENSEARCH_URL)
        except Exception:
            logger.warning(
                "OpenSearch init failed, will retry on next request", exc_info=True
            )
            self._os_client = None

    def _get_os_client(self):
        if self._os_client is not None:
            return self._os_client
        if self._os_enabled:
            self._init_opensearch()
        return self._os_client

    @property
    def hybrid_available(self) -> bool:
        return self._embed_query is not None

    def search(
        self,
        q: str | None,
        k: int = 10,
        page: int = 1,
        mode: str = SearchMode.AUTO,
    ) -> dict[str, Any]:
        if not q:
            return self._empty_result(k)

        if mode == SearchMode.HYBRID and self.hybrid_available:
            return self._hybrid_search(q, k, page)
        elif mode == SearchMode.SEMANTIC and self.hybrid_available:
            return self._vector_search(q, k, page)
        elif mode == SearchMode.AUTO:
            return self._bm25_search(q, k, page)
        else:
            return self._bm25_search(q, k, page)

    def _bm25_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="bm25").inc()
        t0 = time.monotonic()

        client = self._get_os_client()
        if client is not None:
            try:
                result = self._run_opensearch_query(q, k, page)
                SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
                SEARCH_RESULT_COUNT.observe(result.total)
                out = self._format_result(q, result)
                out["mode"] = SearchMode.BM25
                return out
            except Exception:
                logger.warning("OpenSearch BM25 failed", exc_info=True)

        # Fall back to pgvector semantic search when available
        if self._embed_query is not None:
            logger.info("Falling back to pgvector for query: %s", q)
            try:
                result = self._pgvector_search(q, k, page)
                SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
                SEARCH_RESULT_COUNT.observe(result.total)
                fallback_result = self._format_result(q, result)
                fallback_result["fallback"] = True
                fallback_result["mode"] = SearchMode.SEMANTIC
                return fallback_result
            except Exception:
                logger.warning("pgvector fallback also failed", exc_info=True)

        SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
        return self._empty_result(k, q)

    def _hybrid_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="hybrid").inc()
        t0 = time.monotonic()
        timeout = settings.HYBRID_SEARCH_TIMEOUT_SEC

        client = self._get_os_client()
        if client is not None:
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = pool.submit(
                    self._run_opensearch_query, q, k, page, with_embedding=True
                )
                result = future.result(timeout=timeout)
                SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
                SEARCH_RESULT_COUNT.observe(result.total)
                out = self._format_result(q, result)
                out["mode"] = SearchMode.HYBRID
                return out
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Hybrid search timed out after %.1fs, falling back to BM25",
                    timeout,
                )
            except Exception:
                logger.warning(
                    "OpenSearch hybrid failed, falling back to BM25", exc_info=True
                )
            finally:
                pool.shutdown(wait=False)

        return self._bm25_search(q, k, page)

    def _vector_search(self, q: str, k: int = 10, page: int = 1) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="semantic").inc()
        t0 = time.monotonic()
        try:
            result = self._pgvector_search(q, k, page)
        except Exception:
            logger.warning("Vector search failed, falling back to BM25", exc_info=True)
            return self._bm25_search(q, k, page)
        SEARCH_SCORING_DURATION.observe(time.monotonic() - t0)
        SEARCH_RESULT_COUNT.observe(result.total)
        out = self._format_result(q, result)
        out["mode"] = SearchMode.SEMANTIC
        return out

    _PGVECTOR_MAX_PAGE = 10

    def _pgvector_search(self, q: str, k: int, page: int) -> Any:
        """Semantic search using pgvector cosine distance."""
        from shared.embedding import to_pgvector
        from shared.postgres.search import get_connection
        from shared.search_kernel.searcher import SearchHit, SearchResult

        if not q or not q.strip() or self._embed_query is None:
            return SearchResult(
                query=q, total=0, hits=[], page=1, per_page=k, last_page=1
            )

        page = min(page, self._PGVECTOR_MAX_PAGE)

        query_vec = self._embed_query(q)
        vec_str = to_pgvector(query_vec)
        offset = (page - 1) * k
        conn = get_connection()
        try:
            cur = conn.cursor()
            # Fetch k+1 to detect whether more results exist
            cur.execute(
                """
                SELECT pe.url, d.title, d.content,
                       1 - (pe.embedding <=> %s::vector) AS similarity,
                       d.indexed_at, d.published_at
                FROM page_embeddings pe
                JOIN documents d ON d.url = pe.url
                WHERE pe.embedding IS NOT NULL
                ORDER BY pe.embedding <=> %s::vector
                LIMIT %s OFFSET %s
                """,
                (vec_str, vec_str, k + 1, offset),
            )
            rows = cur.fetchall()
            cur.close()
            has_more = len(rows) > k
            rows = rows[:k]
            hits = [
                SearchHit(
                    url=r[0],
                    title=r[1],
                    content=r[2],
                    score=float(r[3]),
                    indexed_at=r[4].isoformat() if r[4] else None,
                    published_at=r[5].isoformat() if r[5] else None,
                )
                for r in rows
            ]
            total = offset + len(hits) + (1 if has_more else 0)
            last_page = min(page + 1 if has_more else page, self._PGVECTOR_MAX_PAGE)
            return SearchResult(
                query=q,
                total=total,
                hits=hits,
                page=page,
                per_page=k,
                last_page=last_page,
            )
        finally:
            conn.close()

    def _format_result(self, q: str, result: Any) -> dict[str, Any]:
        analyzed_q = analyzer.tokenize(q)
        search_terms = analyzed_q.split() if analyzed_q.strip() else [q]

        hits = []
        for hit in result.hits:
            snippet = generate_snippet(hit.content, search_terms)
            hit_dict = {
                "url": hit.url,
                "title": hit.title,
                "snip": snippet.text,
                "snip_plain": snippet.plain_text,
                "rank": hit.score,
            }
            if hit.indexed_at:
                hit_dict["indexed_at"] = hit.indexed_at
            if hit.published_at:
                hit_dict["published_at"] = hit.published_at
            if hit.temporal_anchor is not None:
                hit_dict["temporal_anchor"] = hit.temporal_anchor
            if hit.authorship_clarity is not None:
                hit_dict["authorship_clarity"] = hit.authorship_clarity
            if hit.author:
                hit_dict["author"] = hit.author
            if hit.organization:
                hit_dict["organization"] = hit.organization
            hits.append(hit_dict)

        return {
            "query": q,
            "total": result.total,
            "page": result.page,
            "per_page": result.per_page,
            "last_page": result.last_page,
            "hits": hits,
        }

    def _run_opensearch_query(
        self, q: str, k: int, page: int, *, with_embedding: bool = False
    ) -> Any:
        """Execute OpenSearch query (BM25 or hybrid BM25 + k-NN)."""
        from shared.opensearch.search import CANDIDATE_LIMIT, search_bm25, search_hybrid
        from shared.search_kernel.diversify import diversify_hits
        from shared.search_kernel.searcher import SearchHit, SearchResult, parse_query

        parsed = parse_query(q)
        tokens = analyzer.tokenize(parsed.text) if parsed.text else ""

        if not tokens.strip():
            return SearchResult(
                query=q, total=0, hits=[], page=1, per_page=k, last_page=1
            )

        embedding = None
        if with_embedding and self._embed_query is not None:
            try:
                vec = self._embed_query(q)
                if vec is not None:
                    embedding = vec.tolist()
            except Exception:
                logger.warning("Query embedding failed, using BM25 only", exc_info=True)

        client = self._get_os_client()
        use_diversity = not parsed.site_filter

        if use_diversity:
            # Overscan: fetch extra candidates so we still have enough
            # after per-domain capping.
            fetch_size = min(page * k * settings.DIVERSITY_OVERSCAN, CANDIDATE_LIMIT)
            fetch_offset = 0
        else:
            fetch_size = k
            fetch_offset = (page - 1) * k

        if embedding is not None:
            os_result = search_hybrid(
                client,
                query_tokens=tokens,
                embedding=embedding,
                limit=fetch_size,
                offset=fetch_offset,
                site_filter=parsed.site_filter,
            )
        else:
            os_result = search_bm25(
                client,
                query_tokens=tokens,
                limit=fetch_size,
                offset=fetch_offset,
                site_filter=parsed.site_filter,
            )

        hits = [
            SearchHit(
                url=h["url"],
                title=h["title"],
                content=h["content"],
                score=h["score"],
                indexed_at=h.get("indexed_at"),
                published_at=h.get("published_at"),
                temporal_anchor=h.get("temporal_anchor"),
                authorship_clarity=h.get("authorship_clarity"),
                author=h.get("author"),
                organization=h.get("organization"),
            )
            for h in os_result["hits"]
        ]
        total = os_result["total"]

        if use_diversity:
            diversified = diversify_hits(
                hits,
                limit=page * k,
                max_per_domain=settings.MAX_PER_DOMAIN,
            )
            start = (page - 1) * k
            page_hits = diversified[start : start + k]
            diversified_total = len(diversified)
            if len(hits) >= fetch_size:
                estimated_total = max(total, diversified_total)
            else:
                estimated_total = diversified_total
            last_page = max((estimated_total + k - 1) // k, 1)
            return SearchResult(
                query=q,
                total=estimated_total,
                hits=page_hits,
                page=page,
                per_page=k,
                last_page=last_page,
            )

        last_page = max((total + k - 1) // k, 1)
        return SearchResult(
            query=q,
            total=total,
            hits=hits,
            page=page,
            per_page=k,
            last_page=last_page,
        )

    def get_index_stats(self) -> dict[str, int]:
        """Return index stats: approximate total pages via pg_class."""
        try:
            from shared.postgres.search import get_connection

            con = get_connection(self.db_path)
            cur = con.cursor()
            cur.execute(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = 'documents'"
            )
            row = cur.fetchone()
            count = row[0] if row and row[0] >= 0 else 0
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
