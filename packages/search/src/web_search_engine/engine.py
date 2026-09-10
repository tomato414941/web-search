"""Prepare queries and return OpenSearch's hybrid ranking without overrides."""

from collections.abc import Callable
from opensearchpy import OpenSearch

from web_search_engine.query import empty_search_result, prepare_search_query
from web_search_kernel.searcher import SearchHit, SearchResult
from web_search_opensearch.search import RESULT_WINDOW, operator_filter, search_hybrid


class SearchEngine:
    def __init__(
        self,
        client: OpenSearch,
        embed_query: Callable[[str], list[float]],
        *,
        index: str,
    ):
        self._client = client
        self._embed_query = embed_query
        self._index = index

    def search(self, query: str, limit: int = 10, page: int = 1) -> SearchResult:
        if limit < 1 or page < 1 or (page - 1) * limit >= RESULT_WINDOW:
            raise ValueError(
                f"Requested page exceeds the {RESULT_WINDOW}-result window"
            )
        prepared = prepare_search_query(query)
        if not prepared.has_opensearch_terms:
            return empty_search_result(query, limit)
        filters = operator_filter(
            site=prepared.parsed.site_filter,
            phrases=prepared.tokenized_exact_phrases,
            excluded_terms=prepared.tokenized_exclude_terms,
            excluded_phrases=prepared.tokenized_exclude_phrases,
        )
        result = search_hybrid(
            self._client,
            query_tokens=" ".join(
                part
                for part in (prepared.tokens, *prepared.tokenized_exact_phrases)
                if part
            ),
            vector=self._embed_query(prepared.positive_query),
            limit=limit,
            offset=(page - 1) * limit,
            filters=filters,
            target_index=self._index,
        )
        return SearchResult(
            query=query,
            total=result["total"],
            hits=[SearchHit(**hit) for hit in result["hits"]],
            page=page,
            per_page=limit,
            last_page=max(1, (result["total"] + limit - 1) // limit),
        )
