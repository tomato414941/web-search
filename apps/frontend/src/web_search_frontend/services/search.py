"""Search Service - Frontend search functionality."""

import logging
import time
from typing import Any

from web_search_frontend.metrics import (
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
)
from web_search_frontend.core.config import settings
from web_search_frontend.services.search_opensearch import run_opensearch_query
from web_search_frontend.services.search_query import (
    PreparedSearchQuery,
    prepare_search_query,
)
from web_search_frontend.services.search_response import format_result
from web_search_contracts.enums import SearchMode

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self):
        self._os_client = None
        self._os_enabled = settings.OPENSEARCH_ENABLED
        if self._os_enabled:
            self._init_opensearch()

    def _init_opensearch(self) -> None:
        try:
            from web_search_opensearch.client import get_client
            from web_search_opensearch.mapping import ensure_index

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

    def search(
        self,
        q: str | None,
        k: int = 10,
        page: int = 1,
        mode: str = SearchMode.BM25,
        *,
        include_content: bool = False,
    ) -> dict[str, Any]:
        if not q:
            return self._empty_result(k)
        return self._bm25_search(q, k, page, include_content=include_content)

    def _finalize_search_response(
        self,
        q: str,
        result: Any,
        *,
        mode: str,
        include_content: bool,
        started_at: float,
    ) -> dict[str, Any]:
        SEARCH_SCORING_DURATION.observe(time.monotonic() - started_at)
        SEARCH_RESULT_COUNT.observe(result.total)
        payload = format_result(q, result, include_content=include_content)
        payload["mode"] = mode
        return payload

    def _run_bm25_opensearch(self, q: str, k: int, page: int) -> Any:
        return self._run_opensearch_query(q, k, page)

    def _bm25_search(
        self, q: str, k: int = 10, page: int = 1, *, include_content: bool = False
    ) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode="bm25").inc()
        started_at = time.monotonic()
        try:
            result = self._run_bm25_opensearch(q, k, page)
        except Exception as error:
            logger.warning(
                "OpenSearch BM25 failed",
                exc_info=(type(error), error, error.__traceback__),
            )
            SEARCH_SCORING_DURATION.observe(time.monotonic() - started_at)
            return self._empty_result(
                k, q, degraded=True, error_type="retrieval_failed"
            )
        return self._finalize_search_response(
            q,
            result,
            mode=SearchMode.BM25,
            include_content=include_content,
            started_at=started_at,
        )

    def _parse_search_query(self, q: str) -> PreparedSearchQuery:
        return prepare_search_query(q)

    def _run_opensearch_query(self, q: str, k: int, page: int) -> Any:
        client = self._get_os_client()
        if client is None:
            raise RuntimeError("OpenSearch client unavailable")
        return run_opensearch_query(
            q,
            k,
            page,
            client=client,
            search_query=self._parse_search_query(q),
        )

    def _format_result(
        self, q: str, result: Any, *, include_content: bool = False
    ) -> dict[str, Any]:
        return format_result(q, result, include_content=include_content)

    def _empty_result(
        self,
        k: int,
        q: str = "",
        *,
        degraded: bool = False,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "query": q,
            "total": 0,
            "page": 1,
            "per_page": k,
            "last_page": 1,
            "hits": [],
        }
        if degraded:
            result["degraded"] = True
        if error_type is not None:
            result["error_type"] = error_type
        return result


search_service = SearchService()
