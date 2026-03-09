"""Search Service - Frontend search functionality."""

import logging
import time
from collections.abc import Callable
from typing import Any

from frontend.api.metrics import (
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
)
from frontend.core.config import settings
from frontend.services.search_opensearch import run_opensearch_query
from frontend.services.search_query import (
    PreparedSearchQuery,
    prepare_search_query,
)
from frontend.services.search_response import format_result
from shared.contracts.enums import SearchMode

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
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
        fallback: bool = False,
    ) -> dict[str, Any]:
        SEARCH_SCORING_DURATION.observe(time.monotonic() - started_at)
        SEARCH_RESULT_COUNT.observe(result.total)
        payload = format_result(q, result, include_content=include_content)
        if fallback:
            payload["fallback"] = True
        payload["mode"] = mode
        return payload

    def _log_search_error(
        self,
        error: BaseException,
        handler: str | Callable[[BaseException], None] | None,
    ) -> None:
        if handler is None:
            return
        if callable(handler):
            handler(error)
            return
        logger.warning(
            handler,
            exc_info=(type(error), error, error.__traceback__),
        )

    def _execute_search_flow(
        self,
        q: str,
        k: int,
        *,
        metric_mode: str,
        include_content: bool,
        primary_search: Callable[[], Any],
        primary_mode: str,
        primary_error_handler: str | Callable[[BaseException], None] | None,
        fallback_search: Callable[[], Any] | None = None,
        fallback_mode: str | None = None,
        fallback_error_handler: str | Callable[[BaseException], None] | None = None,
        fallback_returns_payload: bool = False,
        fallback_flag: bool = False,
    ) -> dict[str, Any]:
        SEARCH_QUERY_TOTAL.labels(mode=metric_mode).inc()
        started_at = time.monotonic()

        try:
            result = primary_search()
            return self._finalize_search_response(
                q,
                result,
                mode=primary_mode,
                include_content=include_content,
                started_at=started_at,
            )
        except Exception as error:
            self._log_search_error(error, primary_error_handler)

        if fallback_search is None:
            SEARCH_SCORING_DURATION.observe(time.monotonic() - started_at)
            return self._empty_result(k, q)

        try:
            fallback_result = fallback_search()
            if fallback_returns_payload:
                return fallback_result
            return self._finalize_search_response(
                q,
                fallback_result,
                mode=fallback_mode or primary_mode,
                include_content=include_content,
                started_at=started_at,
                fallback=fallback_flag,
            )
        except Exception as error:
            self._log_search_error(error, fallback_error_handler)
            SEARCH_SCORING_DURATION.observe(time.monotonic() - started_at)
            return self._empty_result(k, q)

    def _run_bm25_opensearch(self, q: str, k: int, page: int) -> Any:
        return self._run_opensearch_query(q, k, page)

    def _bm25_search(
        self, q: str, k: int = 10, page: int = 1, *, include_content: bool = False
    ) -> dict[str, Any]:
        return self._execute_search_flow(
            q,
            k,
            metric_mode="bm25",
            include_content=include_content,
            primary_search=lambda: self._run_bm25_opensearch(q, k, page),
            primary_mode=SearchMode.BM25,
            primary_error_handler="OpenSearch BM25 failed",
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


search_service = SearchService()
