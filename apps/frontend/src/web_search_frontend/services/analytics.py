import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import Request, Response
from web_search_telemetry import SearchResultImpression, SearchTelemetryRepository

from web_search_frontend.core.config import settings
from web_search_contracts.enums import (
    CRAWL_ERROR_STATUSES,
    CrawlAttemptStatus,
    CrawlAttemptSummaryStatus,
    summarize_crawl_attempt_counts,
)
from web_search_core.infrastructure_config import Environment
from web_search_frontend.services.db_helpers import db_cursor
from web_search_postgres.repositories.analytics_repo import AnalyticsRepository

logger = logging.getLogger(__name__)

_repo = AnalyticsRepository
_telemetry_repo = SearchTelemetryRepository

ANON_SESSION_COOKIE = "anon_sid"
ANON_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

CRAWL_ATTEMPT_STATUSES = CRAWL_ERROR_STATUSES + (
    CrawlAttemptStatus.QUEUED_FOR_INDEX,
    CrawlAttemptStatus.BLOCKED,
    CrawlAttemptStatus.SKIPPED,
    "indexed",
)


def get_or_create_anon_session_id(request: Request) -> tuple[str, bool]:
    existing = request.cookies.get(ANON_SESSION_COOKIE)
    if existing:
        return existing, False

    return uuid4().hex, True


def set_anon_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=ANON_SESSION_COOKIE,
        value=session_id,
        max_age=ANON_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.ENVIRONMENT == Environment.PRODUCTION,
        samesite="lax",
    )


def hash_session_id(session_id: str | None) -> str | None:
    if not session_id or not settings.ANALYTICS_SALT:
        return None
    payload = f"{settings.ANALYTICS_SALT}:{session_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snippet_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_impressions(
    hits: list[dict[str, Any]], page: int, per_page: int
) -> list[SearchResultImpression]:
    rank_offset = max(page - 1, 0) * per_page
    impressions: list[SearchResultImpression] = []
    for index, hit in enumerate(hits, start=1):
        impressions.append(
            SearchResultImpression(
                rank=rank_offset + index,
                url=hit["url"],
                title=hit.get("title"),
                score=hit.get("score"),
                snippet_hash=_snippet_hash(hit.get("snip_plain")),
            )
        )
    return impressions


def record_search_telemetry(
    *,
    query: str,
    source: str,
    mode: str,
    page: int,
    limit: int,
    result_count: int,
    latency_ms: int | None,
    session_hash: str | None,
    user_agent: str | None,
    hits: list[dict[str, Any]],
) -> str | None:
    try:
        with db_cursor() as (conn, _):
            request_id, impression_ids = _telemetry_repo.record_search(
                conn,
                query=query,
                source=source,
                mode=mode,
                page=page,
                limit=limit,
                result_count=result_count,
                latency_ms=latency_ms,
                session_hash=session_hash,
                user_agent=user_agent,
                impressions=_build_impressions(hits, page, limit),
            )
        for hit, impression_id in zip(hits, impression_ids):
            hit["impression_id"] = impression_id
        return request_id
    except Exception as exc:
        logger.warning(f"Failed to persist search telemetry: {exc}")
        return None


def record_search_result_click(*, impression_id: str, session_hash: str | None) -> bool:
    try:
        with db_cursor() as (conn, _):
            return _telemetry_repo.record_click(
                conn, impression_id=impression_id, session_hash=session_hash
            )
    except Exception as exc:
        logger.warning(f"Failed to persist search click telemetry: {exc}")
        return False


def get_quality_summary(window_hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_dt = now - timedelta(hours=window_hours)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    cutoff_epoch = int(time.time()) - window_hours * 3600

    search_data = {
        "impressions": 0,
        "zero_hit_rate": 0.0,
        "click_through_rate": 0.0,
        "avg_click_rank": 0.0,
        "p50_ms": 0,
        "p95_ms": 0,
    }
    crawl_data = {
        "indexed_count": 0,
        "pending_count": 0,
        "crawl_success_rate": 0.0,
        "short_content_rate": 0.0,
        "duplicate_content_rate": 0.0,
    }

    with db_cursor() as (conn, _):
        if _repo.table_exists(conn, "search_requests"):
            impression_rows = _telemetry_repo.request_metrics(conn, cutoff_str)

            impressions = len(impression_rows)
            zero_hits = sum(
                1 for _, result_count, _ in impression_rows if result_count == 0
            )
            request_ids = {
                request_id for request_id, _, _ in impression_rows if request_id
            }
            latencies = [
                int(latency) for _, _, latency in impression_rows if latency is not None
            ]

            clicked_request_ids = _telemetry_repo.clicked_request_ids(conn, cutoff_str)
            clicked_impressions = len(request_ids & clicked_request_ids)

            click_ranks = _telemetry_repo.click_ranks(conn, cutoff_str)

            search_data["impressions"] = impressions
            search_data["zero_hit_rate"] = _ratio_percent(zero_hits, impressions)
            search_data["click_through_rate"] = _ratio_percent(
                clicked_impressions, impressions
            )
            search_data["avg_click_rank"] = (
                round(sum(click_ranks) / len(click_ranks), 2) if click_ranks else 0.0
            )
            search_data["p50_ms"] = _percentile(latencies, 0.50)
            search_data["p95_ms"] = _percentile(latencies, 0.95)

        if _repo.table_exists(conn, "documents"):
            indexed_count = _repo.count_indexed_since(conn, cutoff_str)
            crawl_data["indexed_count"] = indexed_count

            short_count = _repo.count_short_content_since(conn, cutoff_str)
            crawl_data["short_content_rate"] = _ratio_percent(
                short_count, indexed_count
            )

            total_with_content, unique_contents = _repo.content_duplicate_counts(
                conn, cutoff_str
            )
            duplicate_count = max(total_with_content - unique_contents, 0)
            crawl_data["duplicate_content_rate"] = _ratio_percent(
                duplicate_count, total_with_content
            )

        if _repo.table_exists(conn, "urls"):
            crawl_data["pending_count"] = _repo.count_pending_urls(conn)

        if _repo.table_exists(conn, "crawl_logs"):
            raw_status_counts = _repo.crawl_status_counts(
                conn, cutoff_epoch, CRAWL_ATTEMPT_STATUSES
            )
            status_counts = summarize_crawl_attempt_counts(raw_status_counts)
            attempts = sum(status_counts.values())
            success = status_counts.get(str(CrawlAttemptSummaryStatus.SUBMITTED), 0)
            crawl_data["crawl_success_rate"] = _ratio_percent(success, attempts)

    return {
        "window": f"{window_hours}h",
        "cutoff_utc": cutoff_str,
        "search": search_data,
        "crawl": crawl_data,
    }


def _ratio_percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    index = int((len(sorted_values) - 1) * q)
    return int(sorted_values[index])
