"""Application entry point for candidate retrieval and ranking.

The caller owns client configuration and lifecycle, error presentation, and
instrumentation. Retrieval failures propagate to that caller.
"""

from opensearchpy import OpenSearch

from web_search_engine.opensearch import run_opensearch_query
from web_search_engine.query import empty_search_result, prepare_search_query
from web_search_kernel.searcher import SearchResult


class SearchEngine:
    def __init__(self, client: OpenSearch, *, index: str = "documents"):
        self._client = client
        self._index = index

    def search(self, query: str, limit: int = 10, page: int = 1) -> SearchResult:
        if not query:
            return empty_search_result(query, limit)
        return run_opensearch_query(
            query,
            limit,
            page,
            client=self._client,
            search_query=prepare_search_query(query),
            target_index=self._index,
        )
