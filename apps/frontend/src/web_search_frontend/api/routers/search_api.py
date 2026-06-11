"""Search API Router - JSON endpoints for search."""

import asyncio
import logging
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from web_search_frontend.core.config import settings
from web_search_frontend.services.search import search_service
from web_search_frontend.services.analytics import (
    get_or_create_anon_session_id,
    hash_session_id,
    record_search_telemetry,
    set_anon_session_cookie,
)
from web_search_frontend.api.middleware.rate_limiter import limiter
from web_search_contracts.enums import SearchMode

logger = logging.getLogger(__name__)


router = APIRouter()


VALID_SEARCH_MODES = {SearchMode.BM25}


# --- Response Models ---


class SearchHit(BaseModel):
    url: str = Field(description="Page URL")
    title: str | None = Field(description="Page title")
    snip: str = Field(description="HTML snippet with `<mark>` highlights")
    snip_plain: str = Field(description="Plain text snippet")
    score: float = Field(description="Relevance score")
    indexed_at: str | None = Field(
        default=None, description="When this page was last indexed (ISO 8601 UTC)"
    )
    published_at: str | None = Field(
        default=None,
        description="When this page was originally published (ISO 8601 UTC)",
    )
    authorship_clarity: float | None = Field(
        default=None,
        description="Authorship clarity score (0.0-1.0)",
    )
    page_rank: float | None = Field(
        default=None,
        description="Page-level link-based rank signal",
    )
    domain_rank: float | None = Field(
        default=None,
        description="Domain-level link-based rank signal",
    )
    word_count: int | None = Field(
        default=None,
        description="Approximate word count of the indexed content",
    )
    link_density: float | None = Field(
        default=None,
        description="Outgoing-link density relative to content length",
    )
    title_present: bool | None = Field(
        default=None,
        description="Whether the page has a non-empty title",
    )
    author: str | None = Field(
        default=None,
        description="Author name extracted from HTML metadata",
    )
    organization: str | None = Field(
        default=None,
        description="Publisher/organization extracted from HTML metadata",
    )
    content: str | None = Field(
        default=None,
        description="Full page text (only when include_content=true)",
    )
    impression_id: str | None = Field(
        default=None,
        description="Search telemetry impression ID for UI click telemetry",
    )


class SearchResponse(BaseModel):
    query: str = Field(description="Normalized search query")
    total: int = Field(description="Total matching documents")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Results per page")
    last_page: int = Field(description="Last available page")
    hits: list[SearchHit] = Field(description="Search results")
    mode: str = Field(description="Actual search mode executed (bm25)")
    requested_mode: str = Field(description="Search mode requested by client (bm25)")
    request_id: str | None = Field(
        default=None, description="Search telemetry request ID"
    )


def _parse_pos_int(value: str | None, default: int, *, min_v: int = 1) -> int:
    try:
        x = int(value) if value is not None else default
    except ValueError:
        x = default
    return max(x, min_v)


@router.get(
    "/search-results",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="Search the web",
)
@limiter.limit("100/minute")
async def api_search(
    request: Request,
    q: str | None = None,
    limit: str | None = None,
    page: str | None = None,
    mode: str | None = None,
    include_content: str | None = None,
):
    """Full-text web search with BM25 ranking and PageRank boosting.

    **Search modes**:
    - `bm25` — keyword-based search

    **Rate limits**: 100 requests/minute (IP-based).
    """
    started_at = time.perf_counter()
    query = (q or "").strip()
    if len(query) > settings.MAX_QUERY_LEN:
        query = query[: settings.MAX_QUERY_LEN]

    per_page = min(_parse_pos_int(limit, settings.RESULTS_LIMIT), settings.MAX_PER_PAGE)
    page_number = min(_parse_pos_int(page, 1), settings.MAX_PAGE)
    search_mode = SearchMode.BM25

    want_content = include_content == "true"

    data = (
        await asyncio.to_thread(
            search_service.search,
            query,
            per_page,
            page_number,
            search_mode,
            include_content=want_content,
        )
        if query
        else search_service._empty_result(per_page)
    )
    data["requested_mode"] = search_mode
    if "mode" not in data:
        data["mode"] = SearchMode.BM25

    should_set_cookie = False
    session_id: str | None = None
    if query:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        user_agent = request.headers.get("user-agent")
        session_id, should_set_cookie = get_or_create_anon_session_id(request)
        session_hash = hash_session_id(session_id)
        request_id = record_search_telemetry(
            query=query,
            source="public_api",
            mode=search_mode,
            page=data["page"],
            limit=data["per_page"],
            result_count=data["total"],
            latency_ms=latency_ms,
            session_hash=session_hash,
            user_agent=user_agent,
            hits=data["hits"],
        )
        if request_id is not None:
            data["request_id"] = request_id

    response = JSONResponse(data)
    if session_id is not None and should_set_cookie:
        set_anon_session_cookie(response, session_id)

    return response
