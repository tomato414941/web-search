"""Search API Router - JSON endpoints for search and prediction."""

import logging
import time
import uuid
import httpx
from fastapi import APIRouter, Request, BackgroundTasks, Response
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
from frontend.api.middleware.rate_limiter import limiter

logger = logging.getLogger(__name__)


router = APIRouter()


def log_search(query: str, result_count: int, user_agent: str | None):
    """Compatibility wrapper used by existing tests."""
    analytics_log_search(query, result_count, user_agent)


def _parse_pos_int(value: str | None, default: int, *, min_v: int = 1) -> int:
    try:
        x = int(value) if value is not None else default
    except ValueError:
        x = default
    return max(x, min_v)


@router.get("/search")
@limiter.limit("100/minute")
async def api_search(
    request: Request,
    background_tasks: BackgroundTasks,
    q: str | None = None,
    limit: str | None = None,
    page: str | None = None,
):
    """Search API (JSON) - uses BM25 + PageRank search."""
    started_at = time.perf_counter()
    query = (q or "").strip()
    if len(query) > settings.MAX_QUERY_LEN:
        query = query[: settings.MAX_QUERY_LEN]

    per_page = min(_parse_pos_int(limit, settings.RESULTS_LIMIT), settings.MAX_PER_PAGE)
    page_number = min(_parse_pos_int(page, 1), settings.MAX_PAGE)

    data = (
        search_service.search(query, per_page, page_number)
        if query
        else search_service._empty_result(per_page)
    )

    if query:
        request_id = uuid.uuid4().hex
        data["request_id"] = request_id

    response = JSONResponse(data)

    if query:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        user_agent = request.headers.get("user-agent")
        session_id = get_or_set_anon_session_id(request, response)
        session_hash = hash_session_id(session_id)

        background_tasks.add_task(log_search, query, data["total"], user_agent)
        background_tasks.add_task(
            log_impression_event,
            query=query,
            request_id=request_id,
            result_count=data["total"],
            session_hash=session_hash,
            latency_ms=latency_ms,
        )

    return response


class SearchClickRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    query: str = Field(min_length=1, max_length=500)
    url: HttpUrl
    rank: int = Field(ge=1, le=1000)


@router.post("/search/click", status_code=204)
@limiter.limit("300/minute")
async def api_search_click(request: Request, payload: SearchClickRequest):
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


@router.get("/predict")
@limiter.limit("30/minute")
async def api_predict(
    request: Request, url: str, parent_score: float = 100.0, visits: int = 0
):
    """
    Predict Crawler Score for a URL.

    Proxies the request to the Crawler Service's scoring endpoint.

    Args:
        url: The URL to evaluate
        parent_score: Score of the parent page (default 100.0)
        visits: Number of times this domain has been visited (default 0)
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/score/predict",
                json={
                    "url": url,
                    "parent_score": parent_score,
                    "visits": visits,
                },
            )
            if resp.status_code == 200:
                return JSONResponse(resp.json())
            else:
                logger.error(f"Crawler service error: {resp.text}")
                return JSONResponse(
                    {"error": "Crawler service unavailable"},
                    status_code=502,
                )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": "Crawler service unavailable", "detail": str(e)},
            status_code=503,
        )
