import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter
import httpx
from frontend.core.config import settings
from frontend.services.search import search_service

logger = logging.getLogger(__name__)

router = APIRouter()

_stats_cache: dict[str, Any] = {"data": None, "expires": 0}
_STATS_TTL = 30


def _crawler_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.INDEXER_API_KEY:
        headers["X-API-Key"] = settings.INDEXER_API_KEY
    return headers


async def _fetch_crawler_stats() -> dict[str, int]:
    """Fetch queue stats from the crawler API."""
    stats: dict[str, int] = {"queued": 0, "visited": 0}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/status",
                headers=_crawler_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                stats["queued"] = data.get("queue_size", data.get("queued", 0))
                stats["visited"] = data.get(
                    "active_seen",
                    data.get("visited", 0),
                )
            else:
                logger.warning(
                    "Crawler stats API returned non-200 status: %s", resp.status_code
                )
    except Exception as e:
        logger.warning("Failed to get crawler stats: %s(%s)", type(e).__name__, e)
    return stats


@router.get("/stats")
async def api_stats():
    """Return System Stats (Queue, Index, etc.)"""
    now = time.monotonic()
    if _stats_cache["data"] is not None and now < _stats_cache["expires"]:
        return _stats_cache["data"]

    loop = asyncio.get_running_loop()
    crawler_stats, db_stats = await asyncio.gather(
        _fetch_crawler_stats(),
        loop.run_in_executor(None, search_service.get_index_stats),
    )

    result = {"queue": crawler_stats, "index": db_stats}
    _stats_cache["data"] = result
    _stats_cache["expires"] = now + _STATS_TTL
    return result
