from typing import Any, Callable

from frontend.services.search_query import PreparedSearchQuery, empty_search_result
from shared.search_kernel.searcher import SearchHit, SearchResult

PGVECTOR_MAX_PAGE = 10


def append_document_filters(
    where_clauses: list[str],
    params: list[Any],
    values: tuple[str, ...],
    *,
    negated: bool = False,
) -> None:
    clause = (
        "NOT (COALESCE(d.title, '') ILIKE %s OR COALESCE(d.content, '') ILIKE %s)"
        if negated
        else "(COALESCE(d.title, '') ILIKE %s OR COALESCE(d.content, '') ILIKE %s)"
    )
    for value in values:
        where_clauses.append(clause)
        value_pattern = f"%{value}%"
        params.extend([value_pattern, value_pattern])


def run_pgvector_search(
    q: str,
    k: int,
    page: int,
    *,
    search_query: PreparedSearchQuery,
    embed_query: Callable[[str], Any] | None,
) -> SearchResult:
    from shared.embedding import to_pgvector
    from shared.postgres.search import get_connection

    if not q or not q.strip() or embed_query is None:
        return empty_search_result(q, k)

    page = min(page, PGVECTOR_MAX_PAGE)
    if not search_query.embedding_query:
        return empty_search_result(q, k)

    query_vec = embed_query(search_query.embedding_query)
    vec_str = to_pgvector(query_vec)
    offset = (page - 1) * k
    where_clauses = ["pe.embedding IS NOT NULL"]
    params: list[Any] = [vec_str]

    if search_query.parsed.site_filter:
        where_clauses.append("d.url ILIKE %s")
        params.append(f"%{search_query.parsed.site_filter}%")

    append_document_filters(where_clauses, params, search_query.exact_phrases)
    append_document_filters(
        where_clauses, params, search_query.exclude_terms, negated=True
    )
    append_document_filters(
        where_clauses, params, search_query.exclude_phrases, negated=True
    )

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT pe.url, d.title, d.content,
                   1 - (pe.embedding <=> %s::vector) AS similarity,
                   d.indexed_at, d.published_at
            FROM page_embeddings pe
            JOIN documents d ON d.url = pe.url
            WHERE {" AND ".join(where_clauses)}
            ORDER BY pe.embedding <=> %s::vector
            LIMIT %s OFFSET %s
            """,
            (*params, vec_str, k + 1, offset),
        )
        rows = cur.fetchall()
        cur.close()
        has_more = len(rows) > k
        rows = rows[:k]
        hits = [
            SearchHit(
                url=row[0],
                title=row[1],
                content=row[2],
                score=float(row[3]),
                indexed_at=row[4].isoformat() if row[4] else None,
                published_at=row[5].isoformat() if row[5] else None,
            )
            for row in rows
        ]
        total = offset + len(hits) + (1 if has_more else 0)
        last_page = min(page + 1 if has_more else page, PGVECTOR_MAX_PAGE)
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
