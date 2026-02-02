"""
Queue Router

Handles queue status and viewing endpoints.
"""

from fastapi import APIRouter, Depends
from app.models.queue import QueueStats, QueueItem
from app.services.queue import QueueService
from app.api.deps import get_queue_service

router = APIRouter()


@router.get("/status", response_model=QueueStats)
async def get_queue_stats(queue_service: QueueService = Depends(get_queue_service)):
    """Get crawl queue statistics"""
    stats = queue_service.get_stats()
    return QueueStats(**stats)


@router.get("/queue", response_model=list[QueueItem])
async def view_queue(
    limit: int = 20, queue_service: QueueService = Depends(get_queue_service)
):
    """View current queue contents"""
    items = queue_service.get_queue_items(limit)
    return [QueueItem(url=item["url"], score=item["score"]) for item in items]
