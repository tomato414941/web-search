import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from web_search_frontend.core.config import settings
from web_search_frontend.services.search import search_service

logger = logging.getLogger(__name__)

router = APIRouter()

_stats_cache: dict[str, Any] = {"data": None, "expires": 0}
_crawler_stats_cache: dict[str, Any] = {"data": None, "expires": 0}
_STATS_TTL = 30
_CRAWLER_STATS_TTL = 120
_CRAWLER_STATS_TIMEOUT_SEC = 10.0


class PublicFrontierStats(BaseModel):
    pending: int = Field(default=0, ge=0)


class PublicIndexStats(BaseModel):
    indexed: int = Field(default=0, ge=0)


class PublicStatsResponse(BaseModel):
    frontier: PublicFrontierStats = Field(default_factory=PublicFrontierStats)
    index: PublicIndexStats = Field(default_factory=PublicIndexStats)


def _crawler_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.INDEXER_API_KEY:
        headers["X-API-Key"] = settings.INDEXER_API_KEY
    return headers


async def _fetch_crawler_stats() -> dict[str, int]:
    """Fetch lightweight frontier stats from the crawler API."""
    now = time.monotonic()
    cached = _crawler_stats_cache["data"]
    empty_stats: dict[str, int] = {"pending": 0}
    try:
        async with httpx.AsyncClient(timeout=_CRAWLER_STATS_TIMEOUT_SEC) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/frontier/summary",
                headers=_crawler_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                stats = {
                    "pending": int(data.get("pending", 0) or 0),
                }
                _crawler_stats_cache["data"] = dict(stats)
                _crawler_stats_cache["expires"] = now + _CRAWLER_STATS_TTL
                return stats
            logger.warning(
                "Crawler stats API returned non-200 status: %s", resp.status_code
            )
    except Exception as e:
        logger.warning("Failed to get crawler stats: %s(%s)", type(e).__name__, e)

    if cached is not None and now < _crawler_stats_cache["expires"]:
        return dict(cached)
    return empty_stats


@router.get("/stats", response_model=PublicStatsResponse)
async def api_stats():
    """Return system stats for frontier and index state."""
    now = time.monotonic()
    if _stats_cache["data"] is not None and now < _stats_cache["expires"]:
        return _stats_cache["data"]

    loop = asyncio.get_running_loop()
    crawler_stats, db_stats = await asyncio.gather(
        _fetch_crawler_stats(),
        loop.run_in_executor(None, search_service.get_index_stats),
    )

    validated = PublicStatsResponse(
        frontier=PublicFrontierStats(**crawler_stats),
        index=PublicIndexStats(**db_stats),
    )
    _stats_cache["data"] = validated
    _stats_cache["expires"] = now + _STATS_TTL
    return validated
