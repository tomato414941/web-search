import logging
from typing import Any, Callable

from frontend.core.config import settings
from frontend.services.search_query import (
    OpenSearchExecutionPlan,
    PreparedSearchQuery,
    build_opensearch_plan,
    empty_search_result,
)
from frontend.services.search_response import build_search_hits
from shared.search_kernel.claim_diversity import diversify_by_claims
from shared.search_kernel.scope_match import (
    classify_document_type,
    classify_query_intent,
    compute_scope_match,
)
from shared.search_kernel.searcher import SearchHit, SearchResult

logger = logging.getLogger(__name__)


def build_query_embedding(
    search_query: PreparedSearchQuery,
    embed_query: Callable[[str], Any] | None,
    *,
    with_embedding: bool,
) -> list[float] | None:
    if not with_embedding or embed_query is None:
        return None
    try:
        vec = embed_query(search_query.embedding_query)
        if vec is None:
            return None
        return vec.tolist()
    except Exception:
        logger.warning("Query embedding failed, using BM25 only", exc_info=True)
        return None


def execute_opensearch_search(
    client: Any,
    search_query: PreparedSearchQuery,
    plan: OpenSearchExecutionPlan,
    embedding: list[float] | None,
) -> dict[str, Any]:
    from shared.opensearch.search import search_bm25, search_hybrid

    search_args = {
        "client": client,
        "query_tokens": search_query.tokens,
        "limit": plan.fetch_size,
        "offset": plan.fetch_offset,
        "site_filter": search_query.parsed.site_filter,
        "exact_phrases": search_query.tokenized_exact_phrases,
        "exclude_terms": search_query.tokenized_exclude_terms,
        "exclude_phrases": search_query.tokenized_exclude_phrases,
    }
    if embedding is not None:
        return search_hybrid(embedding=embedding, **search_args)
    return search_bm25(**search_args)


def apply_scope_match(hits: list[SearchHit], *, query: str) -> str | None:
    intent = classify_query_intent(query)
    if intent.value not in {"tutorial", "troubleshoot"}:
        return intent.value

    for hit in hits:
        doc_type = classify_document_type(hit.url)
        boost = compute_scope_match(intent, doc_type)
        hit.score *= 0.8 + 0.2 * boost
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return intent.value


def build_diversified_result(
    q: str,
    k: int,
    page: int,
    hits: list[SearchHit],
    total: int,
    plan: OpenSearchExecutionPlan,
    *,
    query_intent: str | None,
) -> SearchResult:
    diversity_result = diversify_by_claims(
        hits,
        limit=page * k,
        max_per_domain=settings.MAX_PER_DOMAIN,
    )
    diversified = diversity_result.hits
    start = (page - 1) * k
    page_hits = diversified[start : start + k]
    diversified_total = len(diversified)
    if len(hits) >= plan.fetch_size:
        estimated_total = max(total, diversified_total)
    else:
        estimated_total = diversified_total
    last_page = max((estimated_total + k - 1) // k, 1)

    for hit in page_hits:
        meta = diversity_result.cluster_meta.get(hit.url)
        if meta:
            hit.cluster_id = meta.cluster_id
            hit.sources_agreeing = meta.sources_agreeing

    result = SearchResult(
        query=q,
        total=estimated_total,
        hits=page_hits,
        page=page,
        per_page=k,
        last_page=last_page,
    )
    result.confidence = diversity_result.confidence
    result.perspective_count = diversity_result.perspective_count
    result.query_intent = query_intent
    return result


def build_plain_opensearch_result(
    q: str,
    k: int,
    page: int,
    hits: list[SearchHit],
    total: int,
    *,
    query_intent: str | None,
) -> SearchResult:
    last_page = max((total + k - 1) // k, 1)
    result = SearchResult(
        query=q,
        total=total,
        hits=hits,
        page=page,
        per_page=k,
        last_page=last_page,
    )
    result.query_intent = query_intent
    return result


def run_opensearch_query(
    q: str,
    k: int,
    page: int,
    *,
    client: Any,
    search_query: PreparedSearchQuery,
    embed_query: Callable[[str], Any] | None,
    with_embedding: bool = False,
) -> SearchResult:
    from shared.opensearch.search import CANDIDATE_LIMIT

    if not search_query.has_opensearch_terms:
        return empty_search_result(q, k)

    plan = build_opensearch_plan(
        search_query,
        k,
        page,
        overscan=settings.DIVERSITY_OVERSCAN,
        candidate_limit=CANDIDATE_LIMIT,
    )
    embedding = build_query_embedding(
        search_query, embed_query, with_embedding=with_embedding
    )
    os_result = execute_opensearch_search(client, search_query, plan, embedding)
    hits = build_search_hits(os_result["hits"])
    total = os_result["total"]
    query_intent = apply_scope_match(hits, query=search_query.embedding_query or q)

    if plan.use_diversity:
        return build_diversified_result(
            q,
            k,
            page,
            hits,
            total,
            plan,
            query_intent=query_intent,
        )
    return build_plain_opensearch_result(
        q,
        k,
        page,
        hits,
        total,
        query_intent=query_intent,
    )
