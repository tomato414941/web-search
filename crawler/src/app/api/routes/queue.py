"""
Queue Router

Handles queue status and viewing endpoints.
"""

from fastapi import APIRouter, Depends
from app.models.queue import QueueStats, QueueItem
from app.services.queue import QueueService
from app.api.deps import get_queue_service
from app.core.config import settings

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
    # Get top items from Redis sorted set
    items = queue_service.redis.zrange(
        settings.CRAWL_QUEUE_KEY, 0, limit - 1, withscores=True
    )

    # Convert to QueueItem models
    result = []
    for url, score in items:
        url_str = url.decode() if isinstance(url, bytes) else url
        result.append(QueueItem(url=url_str, score=float(score)))

    return result
