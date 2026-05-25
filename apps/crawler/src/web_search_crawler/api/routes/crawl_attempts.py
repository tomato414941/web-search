"""Crawl error inspection endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query

from web_search_crawler.db.executor import run_in_db_executor
from web_search_contracts.admin_read_models import (
    RecentCrawlErrorsApiResponse,
)

router = APIRouter()

_recent_errors_cache: dict[int, dict[str, Any]] = {}
_RECENT_ERRORS_TTL = 30


def _clear_crawl_attempt_caches() -> None:
    _recent_errors_cache.clear()


@router.get("/crawl-errors/recent", response_model=RecentCrawlErrorsApiResponse)
async def get_recent_crawl_errors(
    limit: int = Query(5, ge=1, le=100, description="Maximum errors to return."),
):
    """Return recent crawl errors."""
    now = time.monotonic()
    cached = _recent_errors_cache.get(limit)
    if cached is not None and now < cached["expires"]:
        return cached["data"]

    from web_search_crawler.utils.history import get_recent_errors

    errors = await run_in_db_executor(get_recent_errors, limit)
    result = RecentCrawlErrorsApiResponse(errors=errors, count=len(errors))
    _recent_errors_cache[limit] = {"data": result, "expires": now + _RECENT_ERRORS_TTL}
    return result
