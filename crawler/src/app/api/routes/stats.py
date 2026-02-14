"""
Stats Router

Aggregated crawler statistics endpoint for dashboard consumption.
"""

from fastapi import APIRouter, Depends
from app.workers.manager import worker_manager
from app.services.queue import QueueService
from app.api.deps import get_queue_service

router = APIRouter()


@router.get("/stats")
async def get_stats(queue_service: QueueService = Depends(get_queue_service)):
    """Return aggregated crawler stats in a single response."""
    from app.utils.history import (
        get_crawl_rate,
        get_error_count,
        get_recent_errors,
        get_status_counts,
    )

    queue_stats = queue_service.get_stats()
    worker_status = await worker_manager.get_status()
    status_counts = get_status_counts(hours=1)
    attempts_count = sum(status_counts.values())
    indexed_count = status_counts.get("indexed", 0) + status_counts.get(
        "queued_for_index", 0
    )
    success_rate = (
        round((indexed_count / attempts_count) * 100, 1) if attempts_count > 0 else 0.0
    )

    return {
        "crawl_rate_1h": get_crawl_rate(hours=1),
        "attempts_count_1h": attempts_count,
        "indexed_count_1h": indexed_count,
        "success_rate_1h": success_rate,
        "error_count_1h": get_error_count(hours=1),
        "recent_errors": get_recent_errors(limit=5),
        "queue_size": queue_stats.get("queue_size", 0),
        "active_seen": queue_stats.get("active_seen", 0),
        "worker_status": worker_status.status,
        "uptime_seconds": worker_status.uptime_seconds,
        "active_tasks": worker_status.active_tasks,
        "concurrency": worker_status.concurrency,
    }
