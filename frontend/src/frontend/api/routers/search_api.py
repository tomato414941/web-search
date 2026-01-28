"""Search API Router - JSON endpoints for search and prediction."""

import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from frontend.core.config import settings
from frontend.core.db import get_connection
from frontend.services.search import search_service
from frontend.api.middleware.rate_limiter import limiter


router = APIRouter()


def log_search(query: str, result_count: int, user_agent: str | None):
    """Log search query to database (runs in background)."""
    try:
        with get_connection(settings.DB_PATH) as conn:
            conn.execute(
                "INSERT INTO search_logs (query, result_count, search_mode, user_agent) VALUES (?, ?, ?, ?)",
                (query, result_count, "hybrid", user_agent),
            )
            conn.commit()
    except Exception:
        pass  # Don't fail search if logging fails


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
    """Search API (JSON) - uses hybrid search (BM25 + Semantic)."""
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

    # Log search in background (non-blocking)
    if query:
        user_agent = request.headers.get("user-agent")
        background_tasks.add_task(log_search, query, data["total"], user_agent)

    return JSONResponse(data)


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
                return JSONResponse(
                    {"error": "Crawler service error", "detail": resp.text},
                    status_code=502,
                )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": "Crawler service unavailable", "detail": str(e)},
            status_code=503,
        )
