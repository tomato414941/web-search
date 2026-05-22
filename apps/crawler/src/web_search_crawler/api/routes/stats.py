"""
Stats Router

Aggregated crawler statistics endpoint for dashboard consumption.
"""

import asyncio
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.api.deps import get_frontier_service
from web_search_crawler.core.events import get_frontier_maintenance_state
from web_search_crawler.services.frontier import FrontierService
from web_search_contracts.admin_read_models import (
    CrawlerStatsApiResponse,
    StatusBreakdownApiResponse,
)
from web_search_contracts.enums import (
    CrawlAttemptSummaryStatus,
    summarize_crawl_attempt_counts,
)

router = APIRouter()

_stats_cache: dict[str, Any] = {"data": None, "expires": 0}
_breakdown_cache: dict[int | None, dict[str, Any]] = {}
_frontier_refresh_lock = asyncio.Lock()
_STATS_TTL = 30
_FRONTIER_TTL = 30
_BREAKDOWN_TTL = 60


def _clear_stats_caches() -> None:
    _stats_cache["data"] = None
    _stats_cache["expires"] = 0
    _breakdown_cache.clear()


def _empty_frontier_snapshot() -> dict[str, Any]:
    return {
        "url_stats": {
            "pending": 0,
            "crawling": 0,
            "done": 0,
            "failed": 0,
            "total": 0,
            "recent": 0,
        },
        "frontier_status_counts": {"pending": 0, "leased": 0},
        "maintenance": get_frontier_maintenance_state(),
    }


async def _build_frontier_stats(frontier_service: FrontierService) -> dict[str, Any]:
    url_store = frontier_service.url_store
    stats = await run_in_db_executor(url_store.get_stats)
    frontier_status_counts = {
        "pending": int(stats.get("pending") or 0),
        "leased": int(stats.get("crawling") or 0),
    }

    return {
        "url_stats": stats,
        "frontier_status_counts": frontier_status_counts,
        "maintenance": get_frontier_maintenance_state(),
    }


async def refresh_frontier_stats_cache(
    frontier_service: FrontierService,
) -> dict[str, Any]:
    async with _frontier_refresh_lock:
        built = await _build_frontier_stats(frontier_service)
        generated_at = int(time.time())
        frontier_status_counts = built.get("frontier_status_counts") or {}
        pending_rows = int(frontier_status_counts.get("pending") or 0)
        leased_rows = int(frontier_status_counts.get("leased") or 0)
        await asyncio.gather(
            run_in_db_executor(
                frontier_service.url_store.write_frontier_snapshot,
                built,
                generated_at=generated_at,
                last_error=None,
            ),
            run_in_db_executor(
                frontier_service.url_store.set_frontier_counters,
                pending_rows=pending_rows,
                leased_rows=leased_rows,
                frontier_rows=pending_rows + leased_rows,
                now=generated_at,
            ),
        )
        payload = await run_in_db_executor(
            frontier_service.url_store.get_frontier_snapshot_payload,
            snapshot_ttl_sec=_FRONTIER_TTL,
            empty_snapshot=_empty_frontier_snapshot(),
            now=generated_at,
        )
        return payload


@router.get("/stats", response_model=CrawlerStatsApiResponse)
async def get_stats(
    frontier_service: FrontierService = Depends(get_frontier_service),
):
    """Return aggregated crawler stats in a single response."""
    now = time.monotonic()
    if _stats_cache["data"] is not None and now < _stats_cache["expires"]:
        return _stats_cache["data"]

    from web_search_crawler.utils.history import (
        get_crawl_rate,
        get_error_count,
        get_recent_errors,
        get_status_counts,
    )

    (
        status_counts,
        crawl_rate,
        error_count,
        recent_errors,
        frontier_summary,
    ) = await asyncio.gather(
        run_in_db_executor(get_status_counts, 1),
        run_in_db_executor(get_crawl_rate, 1),
        run_in_db_executor(get_error_count, 1),
        run_in_db_executor(get_recent_errors, 5),
        run_in_db_executor(
            frontier_service.url_store.get_frontier_dashboard_summary,
            snapshot_ttl_sec=_FRONTIER_TTL,
        ),
    )
    summary_status_counts = summarize_crawl_attempt_counts(status_counts)
    attempts_count = sum(status_counts.values())
    submitted_count = summary_status_counts.get(
        str(CrawlAttemptSummaryStatus.SUBMITTED), 0
    )
    submit_rate = (
        round((submitted_count / attempts_count) * 100, 1)
        if attempts_count > 0
        else 0.0
    )

    result = {
        "crawl_rate_1h": crawl_rate,
        "attempts_count_1h": attempts_count,
        "submitted_count_1h": submitted_count,
        "submit_rate_1h": submit_rate,
        "error_count_1h": error_count,
        "recent_errors": recent_errors,
        "frontier_pending": frontier_summary.get("frontier_pending", 0),
        "leased_tasks": frontier_summary.get("leased_tasks", 0),
        "total_seen": frontier_summary.get("total_seen", 0),
        "frontier_snapshot_age_seconds": frontier_summary.get(
            "frontier_snapshot_age_seconds", 0
        ),
        "frontier_snapshot_stale": frontier_summary.get(
            "frontier_snapshot_stale", True
        ),
    }
    validated = CrawlerStatsApiResponse(**result)
    _stats_cache["data"] = validated
    _stats_cache["expires"] = now + _STATS_TTL
    return validated


@router.get("/stats/breakdown", response_model=StatusBreakdownApiResponse)
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

    from web_search_crawler.utils.history import get_status_counts

    status_counts = await run_in_db_executor(get_status_counts, hours)
    summary_status_counts = summarize_crawl_attempt_counts(status_counts)
    total = sum(summary_status_counts.values())

    submitted = summary_status_counts.get(str(CrawlAttemptSummaryStatus.SUBMITTED), 0)
    submit_rate_pct = round((submitted / total) * 100, 2) if total > 0 else 0.0

    breakdown = sorted(
        [
            {
                "status": status,
                "count": count,
                "pct": round((count / total) * 100, 2) if total > 0 else 0.0,
            }
            for status, count in summary_status_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    result = {
        "total": total,
        "submitted": submitted,
        "submit_rate_pct": submit_rate_pct,
        "hours": hours,
        "breakdown": breakdown,
    }
    validated = StatusBreakdownApiResponse(**result)
    _breakdown_cache[hours] = {"data": validated, "expires": now + _BREAKDOWN_TTL}
    return validated


async def prewarm_admin_stats_caches(frontier_service: FrontierService) -> None:
    await asyncio.gather(
        get_stats(frontier_service),
        refresh_frontier_stats_cache(frontier_service),
    )
