"""
Stats Router

Aggregated crawler statistics endpoint for dashboard consumption.
"""

import asyncio
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from app.db.executor import run_in_db_executor
from app.workers.manager import worker_manager
from app.services.queue import QueueService
from app.api.deps import get_queue_service

router = APIRouter()

_stats_cache: dict[str, Any] = {"data": None, "expires": 0}
_frontier_cache: dict[str, Any] = {"data": None, "expires": 0}
_breakdown_cache: dict[int | None, dict[str, Any]] = {}
_STATS_TTL = 30
_FRONTIER_TTL = 300
_BREAKDOWN_TTL = 60


@router.get("/stats")
async def get_stats(queue_service: QueueService = Depends(get_queue_service)):
    """Return aggregated crawler stats in a single response."""
    now = time.monotonic()
    if _stats_cache["data"] is not None and now < _stats_cache["expires"]:
        return _stats_cache["data"]

    from app.utils.history import (
        get_crawl_rate,
        get_error_count,
        get_recent_errors,
        get_status_counts,
    )

    (
        queue_stats,
        worker_status,
        status_counts,
        crawl_rate,
        error_count,
        recent_errors,
    ) = await asyncio.gather(
        run_in_db_executor(queue_service.get_stats),
        worker_manager.get_status(),
        run_in_db_executor(get_status_counts, 1),
        run_in_db_executor(get_crawl_rate, 1),
        run_in_db_executor(get_error_count, 1),
        run_in_db_executor(get_recent_errors, 5),
    )
    attempts_count = sum(status_counts.values())
    indexed_count = status_counts.get("indexed", 0) + status_counts.get(
        "queued_for_index", 0
    )
    success_rate = (
        round((indexed_count / attempts_count) * 100, 1) if attempts_count > 0 else 0.0
    )

    result = {
        "crawl_rate_1h": crawl_rate,
        "attempts_count_1h": attempts_count,
        "indexed_count_1h": indexed_count,
        "success_rate_1h": success_rate,
        "error_count_1h": error_count,
        "recent_errors": recent_errors,
        "queue_size": queue_stats.get("queue_size", 0),
        "active_seen": queue_stats.get("active_seen", 0),
        "worker_status": worker_status.status,
        "uptime_seconds": worker_status.uptime_seconds,
        "active_tasks": worker_status.active_tasks,
        "concurrency": worker_status.concurrency,
    }
    _stats_cache["data"] = result
    _stats_cache["expires"] = now + _STATS_TTL
    return result


@router.get("/stats/frontier")
async def get_frontier_stats(
    queue_service: QueueService = Depends(get_queue_service),
):
    """Frontier health data for admin dashboard."""
    now = time.monotonic()
    if _frontier_cache["data"] is not None and now < _frontier_cache["expires"]:
        return _frontier_cache["data"]

    from app.utils.history import (
        get_robots_blocked_domains_with_counts,
        get_high_failure_domains,
    )

    url_store = queue_service.url_store
    (
        stats,
        pending_domains,
        done_domains,
        robots_blocked,
        failure_domains,
        stale_count,
    ) = await asyncio.gather(
        run_in_db_executor(url_store.get_stats),
        run_in_db_executor(url_store.get_pending_domains, 15),
        run_in_db_executor(url_store.get_domains, 15),
        run_in_db_executor(get_robots_blocked_domains_with_counts, 24, 3),
        run_in_db_executor(get_high_failure_domains, 24, 5),
        run_in_db_executor(url_store.get_stale_url_count),
    )

    result = {
        "url_stats": stats,
        "pending_domains": pending_domains,
        "done_domains": done_domains,
        "robots_blocked": robots_blocked,
        "failure_domains": failure_domains,
        "stale_count": stale_count,
    }
    _frontier_cache["data"] = result
    _frontier_cache["expires"] = now + _FRONTIER_TTL
    return result


@router.get("/stats/breakdown")
async def get_status_breakdown(
    hours: Optional[int] = Query(
        None, ge=1, description="Time window in hours. Omit for all-time."
    ),
):
    """Status breakdown of crawl attempts."""
    now = time.monotonic()
    cached = _breakdown_cache.get(hours)
    if cached is not None and now < cached["expires"]:
        return cached["data"]

    from app.utils.history import get_status_counts

    status_counts = await run_in_db_executor(get_status_counts, hours)
    total = sum(status_counts.values())

    indexed = status_counts.get("indexed", 0) + status_counts.get("queued_for_index", 0)
    index_rate_pct = round((indexed / total) * 100, 2) if total > 0 else 0.0

    breakdown = sorted(
        [
            {
                "status": status,
                "count": count,
                "pct": round((count / total) * 100, 2) if total > 0 else 0.0,
            }
            for status, count in status_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    result = {
        "total": total,
        "indexed": indexed,
        "index_rate_pct": index_rate_pct,
        "hours": hours,
        "breakdown": breakdown,
    }
    _breakdown_cache[hours] = {"data": result, "expires": now + _BREAKDOWN_TTL}
    return result
