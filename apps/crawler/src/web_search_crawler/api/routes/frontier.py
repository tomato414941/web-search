"""Frontier router."""

import time
from typing import Any

from fastapi import APIRouter, Depends
from web_search_crawler.api.deps import get_frontier_service
from web_search_crawler.models.frontier import FrontierItem, FrontierStats
from web_search_crawler.services.frontier import FrontierService

router = APIRouter()

_status_cache: dict[str, Any] = {"data": None, "expires": 0}
_STATUS_TTL = 30


@router.get("/frontier/status", response_model=FrontierStats)
async def get_frontier_status(
    frontier_service: FrontierService = Depends(get_frontier_service),
):
    """Get frontier summary statistics."""
    now = time.monotonic()
    if _status_cache["data"] is not None and now < _status_cache["expires"]:
        return _status_cache["data"]

    stats = frontier_service.get_frontier_summary()
    result = FrontierStats(**stats)
    _status_cache["data"] = result
    _status_cache["expires"] = now + _STATUS_TTL
    return result


@router.get("/frontier", response_model=list[FrontierItem])
async def view_frontier(
    limit: int = 20, frontier_service: FrontierService = Depends(get_frontier_service)
):
    """Peek current frontier contents."""
    items = frontier_service.get_frontier_items(limit)
    return [FrontierItem(url=item["url"]) for item in items]
