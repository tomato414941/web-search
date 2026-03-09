"""Search API Router - JSON endpoints for search and prediction."""

import asyncio
import logging
import time
import uuid
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from frontend.core.config import settings
from frontend.services.search import search_service
from frontend.services.analytics import (
    get_or_set_anon_session_id,
    hash_session_id,
    log_search as analytics_log_search,
    log_impression_event,
    log_click_event,
)
from frontend.api.deps import optional_api_key
from frontend.api.middleware.rate_limiter import limiter
from shared.contracts.enums import SearchMode

logger = logging.getLogger(__name__)


router = APIRouter()


VALID_SEARCH_MODES = {SearchMode.BM25}


# --- Response Models ---


class SearchHit(BaseModel):
    url: str = Field(description="Page URL")
    title: str | None = Field(description="Page title")
    snip: str = Field(description="HTML snippet with `<mark>` highlights")
    snip_plain: str = Field(description="Plain text snippet")
    rank: float = Field(description="Relevance score")
    indexed_at: str | None = Field(
        default=None, description="When this page was last indexed (ISO 8601 UTC)"
    )
    published_at: str | None = Field(
        default=None,
        description="When this page was originally published (ISO 8601 UTC)",
    )
    temporal_anchor: float | None = Field(
        default=None,
        description="Temporal transparency score (0.0-1.0)",
    )
    authorship_clarity: float | None = Field(
        default=None,
        description="Authorship clarity score (0.0-1.0)",
    )
    factual_density: float | None = Field(
        default=None,
        description="Factual density score (0.0-1.0)",
    )
    origin_score: float | None = Field(
        default=None,
        description="Information origin score (0.0-1.0)",
    )
    origin_type: str | None = Field(
        default=None,
        description="Information origin: spring/river/delta/swamp",
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
        description="Full page text (only when include_content=true with API key)",
    )


class UsageInfo(BaseModel):
    daily_used: int = Field(description="Requests used today")
    daily_limit: int = Field(description="Daily request limit")


class SearchResponse(BaseModel):
    query: str = Field(description="Normalized search query")
    total: int = Field(description="Total matching documents")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Results per page")
    last_page: int = Field(description="Last available page")
    hits: list[SearchHit] = Field(description="Search results")
    mode: str = Field(description="Actual search mode executed (bm25)")
    requested_mode: str = Field(
        description="Search mode requested by client (bm25 or auto)"
    )
    request_id: str | None = Field(
        default=None, description="Request ID for click tracking"
    )
    usage: UsageInfo | None = Field(
        default=None, description="API key usage info (only present with valid key)"
    )


class SearchClickRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    query: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    rank: int = Field(ge=1, le=1000)


def log_search(
    query: str,
    result_count: int,
    user_agent: str | None,
    search_mode: str = "bm25",
    api_key_id: str | None = None,
):
    """Compatibility wrapper used by existing tests."""
    analytics_log_search(
        query, result_count, user_agent, search_mode=search_mode, api_key_id=api_key_id
    )


def _parse_pos_int(value: str | None, default: int, *, min_v: int = 1) -> int:
    try:
        x = int(value) if value is not None else default
    except ValueError:
        x = default
    return max(x, min_v)


@router.get(
    "/search",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="Search the web",
)
@limiter.limit("100/minute")
async def api_search(
    request: Request,
    background_tasks: BackgroundTasks,
    q: str | None = None,
    limit: str | None = None,
    page: str | None = None,
    mode: str | None = None,
    include_content: str | None = None,
    api_key_info: dict | None = Depends(optional_api_key),
):
    """Full-text web search with BM25 ranking and PageRank boosting.

    **Authentication** (optional):
    - Header: `X-API-Key: pbs_...`
    - Query param: `?api_key=pbs_...`

    Anonymous requests are allowed but do not include usage info.

    **Search modes**:
    - `bm25` — keyword-based search
    - `auto` — alias of `bm25`

    **Rate limits**: 100 requests/minute (IP-based), 1000 requests/day (per API key).
    """
    started_at = time.perf_counter()
    query = (q or "").strip()
    if len(query) > settings.MAX_QUERY_LEN:
        query = query[: settings.MAX_QUERY_LEN]

    per_page = min(_parse_pos_int(limit, settings.RESULTS_LIMIT), settings.MAX_PER_PAGE)
    page_number = min(_parse_pos_int(page, 1), settings.MAX_PAGE)
    search_mode = mode if mode in VALID_SEARCH_MODES else SearchMode.AUTO

    want_content = include_content == "true" and api_key_info is not None

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

    if query:
        request_id = uuid.uuid4().hex
        data["request_id"] = request_id

    if api_key_info:
        data["usage"] = {
            "daily_used": api_key_info.get("daily_used", 0) + (1 if query else 0),
            "daily_limit": api_key_info["rate_limit_daily"],
        }

    response = JSONResponse(data)

    api_key_id = api_key_info["id"] if api_key_info else None

    if query:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        user_agent = request.headers.get("user-agent")
        session_id = get_or_set_anon_session_id(request, response)
        session_hash = hash_session_id(session_id)

        background_tasks.add_task(
            log_search, query, data["total"], user_agent, search_mode, api_key_id
        )
        background_tasks.add_task(
            log_impression_event,
            query=query,
            request_id=request_id,
            result_count=data["total"],
            session_hash=session_hash,
            latency_ms=latency_ms,
        )

    return response


@router.post(
    "/search/click",
    status_code=204,
    summary="Log a click event",
)
@limiter.limit("300/minute")
async def api_search_click(request: Request, payload: SearchClickRequest):
    """Record that a user clicked a search result. Used for relevance feedback."""
    response = Response(status_code=204)
    session_id = get_or_set_anon_session_id(request, response)
    session_hash = hash_session_id(session_id)

    log_click_event(
        query=payload.query,
        request_id=payload.request_id,
        clicked_url=str(payload.url),
        clicked_rank=payload.rank,
        session_hash=session_hash,
    )
    return response
