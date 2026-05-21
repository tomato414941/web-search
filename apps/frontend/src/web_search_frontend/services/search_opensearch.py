import logging
from dataclasses import replace
from typing import Any

from web_search_frontend.services.search_query import (
    OpenSearchExecutionPlan,
    PreparedSearchQuery,
    build_opensearch_plan,
    empty_search_result,
)
from web_search_frontend.services.search_ranking_policy import (
    SearchRankingPolicy,
    candidate_window_size,
    canonical_paths_for_policy,
    classify_query_policy,
    rerank_hits,
)
from web_search_frontend.services.search_response import build_search_hits
from web_search_kernel.analyzer import analyzer
from web_search_kernel.searcher import SearchHit, SearchResult

logger = logging.getLogger(__name__)

CANONICAL_HOST_BOOST = 3.0
CANONICAL_EXACT_PATH_BOOST = 5.0
CANONICAL_PATH_BOOST = 4.0
CANONICAL_HOMEPAGE_BOOST = 6.0
COMPARISON_SUBJECTS_BOOST = 4.0
COMPARISON_TITLE_BOOST = 6.0
COMPARISON_PHRASE_BOOST = 7.0
COMPARISON_CUE_BOOST = 3.0


def _rewrite_search_query_for_policy(
    search_query: PreparedSearchQuery,
    *,
    policy: SearchRankingPolicy,
) -> PreparedSearchQuery:
    if policy.query_class == "comparison" and policy.comparison is not None:
        comparison_query = " ".join(policy.comparison.subjects)
        rewritten_tokens = analyzer.tokenize(comparison_query).strip()
        if rewritten_tokens and rewritten_tokens != search_query.tokens:
            return replace(
                search_query,
                tokens=rewritten_tokens,
                positive_query=comparison_query,
            )

    if policy.source is None or not policy.source.retrieval_query:
        return search_query

    rewritten_tokens = analyzer.tokenize(policy.source.retrieval_query).strip()
    if not rewritten_tokens or rewritten_tokens == search_query.tokens:
        return search_query

    return replace(
        search_query,
        tokens=rewritten_tokens,
        positive_query=policy.source.retrieval_query,
    )


def execute_opensearch_search(
    client: Any,
    search_query: PreparedSearchQuery,
    plan: OpenSearchExecutionPlan,
    required_domains: tuple[str, ...] = (),
    retrieval_boosts: Any = None,
) -> dict[str, Any]:
    from web_search_opensearch.search import search_bm25

    search_args = {
        "client": client,
        "query_tokens": search_query.tokens,
        "limit": plan.fetch_size,
        "offset": plan.fetch_offset,
        "site_filter": search_query.parsed.site_filter,
        "exact_phrases": search_query.tokenized_exact_phrases,
        "exclude_terms": search_query.tokenized_exclude_terms,
        "exclude_phrases": search_query.tokenized_exclude_phrases,
        "required_domains": required_domains,
        "retrieval_boosts": retrieval_boosts,
    }
    return search_bm25(**search_args)


def _retrieval_boosts_for_policy(policy: SearchRankingPolicy) -> Any:
    from web_search_opensearch.search import (
        HostPathBoosts,
        RetrievalBoosts,
        SubjectPhraseBoosts,
    )

    host_path = None
    if policy.source is not None:
        host_path = HostPathBoosts(
            hosts=policy.source.domains,
            paths=canonical_paths_for_policy(policy),
            host_boost=CANONICAL_HOST_BOOST,
            exact_path_boost=CANONICAL_EXACT_PATH_BOOST,
            path_prefix_boost=CANONICAL_PATH_BOOST,
            homepage_boost=CANONICAL_HOMEPAGE_BOOST,
        )

    subject_phrase = None
    if policy.query_class == "comparison" and policy.comparison is not None:
        subject_phrase = SubjectPhraseBoosts(
            subjects=policy.comparison.subjects,
            subjects_boost=COMPARISON_SUBJECTS_BOOST,
            title_boost=COMPARISON_TITLE_BOOST,
            phrase_boost=COMPARISON_PHRASE_BOOST,
            cue_boost=COMPARISON_CUE_BOOST,
        )

    if host_path is None and subject_phrase is None:
        return None
    return RetrievalBoosts(host_path=host_path, subject_phrase=subject_phrase)


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
    from web_search_opensearch.search import CANDIDATE_LIMIT

    if not search_query.has_opensearch_terms:
        return empty_search_result(q, k)

    policy = classify_query_policy(q, search_query)
    retrieval_query = _rewrite_search_query_for_policy(search_query, policy=policy)
    plan = build_opensearch_plan(
        retrieval_query,
        candidate_window_size(k, page, policy, candidate_limit=CANDIDATE_LIMIT),
        page,
        overscan=0,
        candidate_limit=CANDIDATE_LIMIT,
    )
    canonical_domains = policy.source.domains if policy.source is not None else ()
    required_domains = canonical_domains if policy.restrict_to_source else ()
    os_result = execute_opensearch_search(
        client,
        retrieval_query,
        plan,
        required_domains=required_domains,
        retrieval_boosts=_retrieval_boosts_for_policy(policy),
    )
    hits = rerank_hits(build_search_hits(os_result["hits"]), policy, limit=k)
    total = os_result["total"]
    return build_plain_opensearch_result(q, k, page, hits, total)
