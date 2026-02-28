"""
Search Engine

Provides vector (semantic) search using pgvector.
BM25 and hybrid search are handled by OpenSearch.
"""

import re
from dataclasses import dataclass
from typing import Callable

import numpy as np

from shared.postgres.search import get_connection
from shared.embedding import to_pgvector

EmbeddingFunc = Callable[[str], np.ndarray]


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


@dataclass
class ParsedQuery:
    """Parsed query with operators extracted."""

    text: str
    site_filter: str | None = None


_SITE_RE = re.compile(r"\bsite:(\S+)", re.IGNORECASE)


def parse_query(raw: str) -> ParsedQuery:
    """Extract query operators (site:) from raw query string."""
    site_filter = None
    match = _SITE_RE.search(raw)
    if match:
        site_filter = match.group(1).lower()
        raw = raw[: match.start()] + raw[match.end() :]
    return ParsedQuery(text=raw.strip(), site_filter=site_filter)


class SearchEngine:
    """Search engine providing vector search via pgvector."""

    def __init__(
        self,
        db_path: str,
        embed_query_func: EmbeddingFunc | None = None,
        **_kwargs,
    ):
        self.db_path = db_path
        self._embed_query = embed_query_func

    def vector_search(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
    ) -> SearchResult:
        """Semantic search using vector embeddings via pgvector."""
        if not query or not query.strip():
            return self._empty_result(query, limit)

        if self._embed_query is None:
            return self._empty_result(query, limit)

        query_vec = self._embed_query(query)

        return self._vector_search_pgvector(query, query_vec, limit, page)

    def _vector_search_pgvector(
        self,
        query: str,
        query_vec: np.ndarray,
        limit: int,
        page: int,
    ) -> SearchResult:
        """Vector search using pgvector <=> cosine distance operator."""
        vec_str = to_pgvector(query_vec)
        offset = (page - 1) * limit
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM page_embeddings WHERE embedding IS NOT NULL"
            )
            total = cur.fetchone()[0]

            cur.execute(
                """
                SELECT pe.url, d.title, d.content,
                       1 - (pe.embedding <=> %s::vector) AS similarity
                FROM page_embeddings pe
                JOIN documents d ON d.url = pe.url
                WHERE pe.embedding IS NOT NULL
                ORDER BY pe.embedding <=> %s::vector
                LIMIT %s OFFSET %s
                """,
                (vec_str, vec_str, limit, offset),
            )
            rows = cur.fetchall()
            cur.close()

            hits = [
                SearchHit(url=row[0], title=row[1], content=row[2], score=float(row[3]))
                for row in rows
            ]

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
