"""Crawl attempt inspection endpoints."""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Query

from web_search_crawler.db.executor import run_in_db_executor
from web_search_contracts.admin_read_models import (
    RecentCrawlErrorsApiResponse,
    StatusBreakdownApiResponse,
)
from web_search_contracts.enums import (
    CrawlAttemptSummaryStatus,
    summarize_crawl_attempt_counts,
)

router = APIRouter()

_breakdown_cache: dict[int | None, dict[str, Any]] = {}
_recent_errors_cache: dict[int, dict[str, Any]] = {}
_BREAKDOWN_TTL = 60
_RECENT_ERRORS_TTL = 30


def _clear_crawl_attempt_caches() -> None:
    _breakdown_cache.clear()
    _recent_errors_cache.clear()


@router.get("/crawl-attempts/breakdown", response_model=StatusBreakdownApiResponse)
async def get_status_breakdown(
    hours: Optional[int] = Query(
        None, ge=1, description="Time window in hours. Omit for all-time."
    ),
):
    """Return crawl attempt status buckets."""
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

    result = StatusBreakdownApiResponse(
        total=total,
        submitted=submitted,
        submit_rate_pct=submit_rate_pct,
        hours=hours,
        breakdown=breakdown,
    )
    _breakdown_cache[hours] = {"data": result, "expires": now + _BREAKDOWN_TTL}
    return result


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
