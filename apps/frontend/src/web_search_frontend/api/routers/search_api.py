"""Search API Router - JSON endpoints for search."""

import asyncio
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator

from web_search_frontend.core.config import settings
from web_search_frontend.services.search import search_service, SearchUnavailable
from web_search_opensearch.search import RESULT_WINDOW
from web_search_frontend.services.analytics import (
    record_search_telemetry,
)
from web_search_frontend.api.middleware.rate_limiter import limiter


router = APIRouter()


# --- Response Models ---


class SearchHit(BaseModel):
    url: str = Field(description="Page URL")
    title: str | None = Field(description="Page title")
    snip: str = Field(description="HTML snippet with `<mark>` highlights")
    snip_plain: str = Field(description="Plain text snippet")
    score: float = Field(description="Relevance score")
    content: str | None = Field(
        default=None,
        description="Stored search excerpt, at most 20,000 characters (include_content=true)",
    )


class SearchResponse(BaseModel):
    query: str = Field(description="Normalized search query")
    total: int = Field(description="Accessible hybrid results, capped at 200")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Results per page")
    last_page: int = Field(description="Last available page")
    hits: list[SearchHit] = Field(description="Search results")
    mode: Literal["hybrid"]
    request_id: str | None = Field(
        default=None, description="Search telemetry request ID"
    )


class SearchParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(default="", max_length=settings.MAX_QUERY_LEN)
    limit: int = Field(default=settings.RESULTS_LIMIT, ge=1, le=settings.MAX_PER_PAGE)
    page: int = Field(default=1, ge=1)
    include_content: bool = False

    @model_validator(mode="after")
    def check_result_window(self):
        if (self.page - 1) * self.limit >= RESULT_WINDOW:
            raise ValueError(
                f"Requested page exceeds the {RESULT_WINDOW}-result window"
            )
        return self


@router.get(
    "/search-results",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    responses={503: {"description": "Hybrid search unavailable"}},
    summary="Search the web",
)
@limiter.limit("100/minute")
async def api_search(request: Request, params: Annotated[SearchParameters, Query()]):
    """Hybrid keyword and vector search. Rate limit: 100 requests/minute per IP."""
    started_at = time.perf_counter()
    query = params.q.strip()
    try:
        data = await asyncio.to_thread(
            search_service.search,
            query,
            params.limit,
            params.page,
            include_content=params.include_content,
        )
    except SearchUnavailable:
        raise HTTPException(
            status_code=503, detail="Search is temporarily unavailable"
        ) from None

    if query:
        request_id = await asyncio.to_thread(
            record_search_telemetry,
            query=query,
            source="public_api",
            mode="hybrid",
            page=data["page"],
            limit=data["per_page"],
            result_count=data["total"],
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            session_hash=None,
            user_agent=request.headers.get("user-agent"),
        )
        if request_id is not None:
            data["request_id"] = request_id
    return SearchResponse(**data)
