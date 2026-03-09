import logging
from typing import Any

from frontend.services.search_query import (
    OpenSearchExecutionPlan,
    PreparedSearchQuery,
    build_opensearch_plan,
    empty_search_result,
)
from frontend.services.search_ranking_policy import (
    candidate_window_size,
    canonical_paths_for_policy,
    classify_query_policy,
    rerank_hits,
)
from frontend.services.search_response import build_search_hits
from shared.search_kernel.searcher import SearchHit, SearchResult

logger = logging.getLogger(__name__)


def execute_opensearch_search(
    client: Any,
    search_query: PreparedSearchQuery,
    plan: OpenSearchExecutionPlan,
    canonical_domains: tuple[str, ...] = (),
    canonical_paths: tuple[str, ...] = (),
) -> dict[str, Any]:
    from shared.opensearch.search import search_bm25

    search_args = {
        "client": client,
        "query_tokens": search_query.tokens,
        "limit": plan.fetch_size,
        "offset": plan.fetch_offset,
        "site_filter": search_query.parsed.site_filter,
        "exact_phrases": search_query.tokenized_exact_phrases,
        "exclude_terms": search_query.tokenized_exclude_terms,
        "exclude_phrases": search_query.tokenized_exclude_phrases,
        "canonical_domains": canonical_domains,
        "canonical_paths": canonical_paths,
    }
    return search_bm25(**search_args)


def build_plain_opensearch_result(
    q: str, k: int, page: int, hits: list[SearchHit], total: int
) -> SearchResult:
    last_page = max((total + k - 1) // k, 1)
    return SearchResult(
        query=q,
        total=total,
        hits=hits,
        page=page,
        per_page=k,
        last_page=last_page,
    )


def run_opensearch_query(
    q: str,
    k: int,
    page: int,
    *,
    client: Any,
    search_query: PreparedSearchQuery,
) -> SearchResult:
    from shared.opensearch.search import CANDIDATE_LIMIT

    if not search_query.has_opensearch_terms:
        return empty_search_result(q, k)

    policy = classify_query_policy(q, search_query)
    plan = build_opensearch_plan(
        search_query,
        candidate_window_size(k, page, policy, candidate_limit=CANDIDATE_LIMIT),
        page,
        overscan=0,
        candidate_limit=CANDIDATE_LIMIT,
    )
    canonical_domains = policy.source.domains if policy.source is not None else ()
    canonical_paths = canonical_paths_for_policy(policy)
    os_result = execute_opensearch_search(
        client,
        search_query,
        plan,
        canonical_domains=canonical_domains,
        canonical_paths=canonical_paths,
    )
    hits = rerank_hits(build_search_hits(os_result["hits"]), policy, limit=k)
    total = os_result["total"]
    return build_plain_opensearch_result(q, k, page, hits, total)
