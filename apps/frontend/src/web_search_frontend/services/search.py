"""Runtime wiring, metrics, and presentation for native hybrid search."""

import logging
import time
from typing import Any

from web_search_frontend.metrics import (
    SEARCH_QUERY_TOTAL,
    SEARCH_RESULT_COUNT,
    SEARCH_SCORING_DURATION,
)
from web_search_frontend.core.config import settings
from web_search_engine import SearchEngine
from web_search_kernel.searcher import SearchResult
from web_search_frontend.services.search_response import format_result

logger = logging.getLogger(__name__)


class SearchUnavailable(RuntimeError):
    pass


class SearchService:
    def __init__(self, engine: SearchEngine | None = None):
        self._engine = engine

    def _get_search_engine(self) -> SearchEngine:
        if self._engine is None:
            from web_search_opensearch.client import get_client, index_name
            from web_search_opensearch.embeddings import get_embeddings
            from web_search_opensearch.mapping import validate_index

            client = get_client(settings.OPENSEARCH_URL)
            validate_index(client)
            self._engine = SearchEngine(
                client, get_embeddings().query, index=index_name()
            )
        return self._engine

    def search(
        self,
        q: str | None,
        k: int = 10,
        page: int = 1,
        *,
        include_content: bool = False,
    ) -> dict[str, Any]:
        if not q:
            result = SearchResult(
                query="", total=0, hits=[], page=1, per_page=k, last_page=1
            )
        else:
            SEARCH_QUERY_TOTAL.labels(mode="hybrid").inc()
            started_at = time.monotonic()
            try:
                result = self._get_search_engine().search(q, k, page)
            except Exception as error:
                logger.warning("Hybrid search failed", exc_info=True)
                raise SearchUnavailable("Search is temporarily unavailable") from error
            finally:
                SEARCH_SCORING_DURATION.observe(time.monotonic() - started_at)
            SEARCH_RESULT_COUNT.observe(result.total)
        payload = format_result(q or "", result, include_content=include_content)
        payload["mode"] = "hybrid"
        return payload


search_service = SearchService()
