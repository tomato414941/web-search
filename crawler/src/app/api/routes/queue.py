"""
Queue Router

Handles queue status and viewing endpoints.
"""

import time
from typing import Any

from fastapi import APIRouter, Depends
from app.models.queue import QueueStats, QueueItem
from app.services.queue import QueueService
from app.api.deps import get_queue_service

router = APIRouter()

_status_cache: dict[str, Any] = {"data": None, "expires": 0}
_STATUS_TTL = 30


@router.get("/status", response_model=QueueStats)
async def get_queue_stats(queue_service: QueueService = Depends(get_queue_service)):
    """Get crawl queue statistics"""
    now = time.monotonic()
    if _status_cache["data"] is not None and now < _status_cache["expires"]:
        return _status_cache["data"]

    stats = queue_service.get_stats()
    result = QueueStats(**stats)
    _status_cache["data"] = result
    _status_cache["expires"] = now + _STATUS_TTL
    return result


@router.get("/queue", response_model=list[QueueItem])
async def view_queue(
    limit: int = 20, queue_service: QueueService = Depends(get_queue_service)
):
    """View current queue contents"""
    items = queue_service.get_queue_items(limit)
    return [QueueItem(url=item["url"]) for item in items]
