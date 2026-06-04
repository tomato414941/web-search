"""Search telemetry ingestion endpoints."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from web_search_frontend.api.middleware.rate_limiter import limiter
from web_search_frontend.services.analytics import (
    get_or_create_anon_session_id,
    hash_session_id,
    record_search_result_click,
    set_anon_session_cookie,
)

router = APIRouter()


class SearchResultClickRequest(BaseModel):
    impression_id: str = Field(min_length=8, max_length=128)


@router.post("/events/search-result-clicked", status_code=204)
@limiter.limit("300/minute")
async def search_result_click(request: Request, payload: SearchResultClickRequest):
    """Record that a user clicked a previously displayed search result."""
    response = Response(status_code=204)
    session_id, should_set_cookie = get_or_create_anon_session_id(request)
    session_hash = hash_session_id(session_id)
    recorded = record_search_result_click(
        impression_id=payload.impression_id,
        session_hash=session_hash,
    )
    if should_set_cookie:
        set_anon_session_cookie(response, session_id)
    if not recorded:
        return Response(status_code=404)
    return response
