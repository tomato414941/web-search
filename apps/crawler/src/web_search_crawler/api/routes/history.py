from typing import Optional

from fastapi import APIRouter, Query

from web_search_crawler.db.executor import run_in_db_executor
from web_search_crawler.models.history import CrawlHistoryAdminEntry, CrawlHistoryEntry
from web_search_contracts.enums import (
    CrawlAttemptSummaryStatus,
    summarize_crawl_attempt_status,
)

router = APIRouter()


def _status_tone(summary_status: str) -> str:
    tone_map = {
        str(CrawlAttemptSummaryStatus.SUBMITTED): "success",
        str(CrawlAttemptSummaryStatus.BLOCKED): "warn",
        str(CrawlAttemptSummaryStatus.SKIPPED): "warn",
        str(CrawlAttemptSummaryStatus.RETRYING): "warn",
        str(CrawlAttemptSummaryStatus.FAILED): "error",
    }
    return tone_map.get(summary_status, "info")


def _to_admin_history_entry(entry: dict) -> CrawlHistoryAdminEntry:
    raw_status = str(entry.get("status") or "unknown")
    status_label = summarize_crawl_attempt_status(raw_status)
    return CrawlHistoryAdminEntry(
        id=int(entry["id"]),
        url=str(entry["url"]),
        raw_status=raw_status,
        status_label=status_label,
        status_tone=_status_tone(status_label),
        http_code=entry.get("http_code"),
        error_message=entry.get("error_message"),
        precheck_ms=entry.get("precheck_ms"),
        robots_ms=entry.get("robots_ms"),
        ssrf_ms=entry.get("ssrf_ms"),
        crawl_delay_ms=entry.get("crawl_delay_ms"),
        fetch_ms=entry.get("fetch_ms"),
        fetch_request_ms=entry.get("fetch_request_ms"),
        fetch_body_read_ms=entry.get("fetch_body_read_ms"),
        parse_ms=entry.get("parse_ms"),
        submit_ms=entry.get("submit_ms"),
        total_ms=entry.get("total_ms"),
        created_at=int(entry["created_at"]),
    )


@router.get("/history", response_model=list[CrawlHistoryEntry])
async def get_crawl_history(
    url: Optional[str] = Query(None, description="Filter by specific URL"),
    limit: int = Query(
        50, ge=1, le=1000, description="Maximum number of records to return"
    ),
):
    """
    Get crawl history

    Returns recent crawl attempts with status, timestamps, and error information.
    """
    from web_search_crawler.utils.history import get_recent_history, get_url_history

    if url:
        return await run_in_db_executor(get_url_history, url, limit)
    else:
        return await run_in_db_executor(get_recent_history, limit)


@router.get("/history/admin", response_model=list[CrawlHistoryAdminEntry])
async def get_admin_crawl_history(
    url: Optional[str] = Query(None, description="Filter by specific URL"),
    limit: int = Query(
        50, ge=1, le=1000, description="Maximum number of records to return"
    ),
):
    """Return operator-facing crawl history entries for admin pages."""
    from web_search_crawler.utils.history import get_recent_history, get_url_history

    if url:
        history = await run_in_db_executor(get_url_history, url, limit)
    else:
        history = await run_in_db_executor(get_recent_history, limit)
    return [_to_admin_history_entry(entry) for entry in history]
