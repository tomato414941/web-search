import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request, Response

from frontend.core.config import settings
from shared.core.infrastructure_config import Environment
from shared.db.search import (
    get_connection,
    is_postgres_mode,
    sql_placeholder,
    sql_placeholders,
)

logger = logging.getLogger(__name__)

ANON_SESSION_COOKIE = "anon_sid"
ANON_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

CRAWL_ERROR_STATUSES = (
    "indexer_error",
    "http_error",
    "unknown_error",
    "dead_letter",
)
CRAWL_ATTEMPT_STATUSES = CRAWL_ERROR_STATUSES + ("indexed", "blocked", "skipped")


def normalize_query(query: str) -> str:
    return " ".join((query or "").strip().lower().split())


def get_or_set_anon_session_id(request: Request, response: Response) -> str:
    existing = request.cookies.get(ANON_SESSION_COOKIE)
    if existing:
        return existing

    session_id = uuid.uuid4().hex
    response.set_cookie(
        key=ANON_SESSION_COOKIE,
        value=session_id,
        max_age=ANON_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.ENVIRONMENT == Environment.PRODUCTION,
        samesite="lax",
    )
    return session_id


def hash_session_id(session_id: str | None) -> str | None:
    if not session_id or not settings.ANALYTICS_SALT:
        return None
    payload = f"{settings.ANALYTICS_SALT}:{session_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_search(query: str, result_count: int, user_agent: str | None) -> None:
    conn = None
    try:
        ph = sql_placeholder()
        conn = get_connection(settings.DB_PATH)
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO search_logs (query, result_count, search_mode, user_agent) VALUES ({ph}, {ph}, {ph}, {ph})",
            (query, result_count, "bm25", user_agent),
        )
        conn.commit()
        cur.close()
    except Exception as exc:
        logger.warning(f"Failed to persist search log: {exc}")
    finally:
        if conn is not None:
            conn.close()


def log_impression_event(
    *,
    query: str,
    request_id: str,
    result_count: int,
    session_hash: str | None,
    latency_ms: int | None,
) -> None:
    _log_search_event(
        event_type="impression",
        query=query,
        request_id=request_id,
        session_hash=session_hash,
        result_count=result_count,
        clicked_url=None,
        clicked_rank=None,
        latency_ms=latency_ms,
    )


def log_click_event(
    *,
    query: str,
    request_id: str,
    clicked_url: str,
    clicked_rank: int,
    session_hash: str | None,
) -> None:
    _log_search_event(
        event_type="click",
        query=query,
        request_id=request_id,
        session_hash=session_hash,
        result_count=None,
        clicked_url=clicked_url,
        clicked_rank=clicked_rank,
        latency_ms=None,
    )


def _log_search_event(
    *,
    event_type: str,
    query: str,
    request_id: str | None,
    session_hash: str | None,
    result_count: int | None,
    clicked_url: str | None,
    clicked_rank: int | None,
    latency_ms: int | None,
) -> None:
    conn = None
    try:
        ph = sql_placeholder()
        conn = get_connection(settings.DB_PATH)
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO search_events (
                event_type, query, query_norm, request_id, session_hash,
                result_count, clicked_url, clicked_rank, latency_ms
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
            (
                event_type,
                query,
                normalize_query(query),
                request_id,
                session_hash,
                result_count,
                clicked_url,
                clicked_rank,
                latency_ms,
            ),
        )
        conn.commit()
        cur.close()
    except Exception as exc:
        logger.warning(f"Failed to persist search event '{event_type}': {exc}")
    finally:
        if conn is not None:
            conn.close()


def get_quality_summary(window_hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_dt = now - timedelta(hours=window_hours)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    cutoff_epoch = int(time.time()) - window_hours * 3600
    postgres_mode = is_postgres_mode()
    ph = sql_placeholder()

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

    conn = get_connection(settings.DB_PATH)
    try:
        cur = conn.cursor()

        if _table_exists(conn, "search_events"):
            time_filter = (
                f"created_at >= {ph}"
                if postgres_mode
                else f"datetime(created_at) >= datetime({ph})"
            )

            cur.execute(
                f"""
                SELECT request_id, result_count, latency_ms
                FROM search_events
                WHERE event_type = {ph} AND {time_filter}
                """,
                ("impression", cutoff_str),
            )
            impression_rows = cur.fetchall()

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

            cur.execute(
                f"""
                SELECT DISTINCT request_id
                FROM search_events
                WHERE event_type = {ph} AND {time_filter} AND request_id IS NOT NULL
                """,
                ("click", cutoff_str),
            )
            clicked_request_ids = {row[0] for row in cur.fetchall() if row[0]}
            clicked_impressions = len(request_ids & clicked_request_ids)

            cur.execute(
                f"""
                SELECT clicked_rank
                FROM search_events
                WHERE event_type = {ph} AND {time_filter} AND clicked_rank IS NOT NULL
                """,
                ("click", cutoff_str),
            )
            click_ranks = [int(row[0]) for row in cur.fetchall() if row[0] is not None]

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

        if _table_exists(conn, "documents"):
            indexed_filter = (
                f"indexed_at >= {ph}"
                if postgres_mode
                else f"datetime(indexed_at) >= datetime({ph})"
            )

            cur.execute(
                f"SELECT COUNT(*) FROM documents WHERE indexed_at IS NOT NULL AND {indexed_filter}",
                (cutoff_str,),
            )
            indexed_count = int(cur.fetchone()[0] or 0)
            crawl_data["indexed_count"] = indexed_count

            cur.execute(
                f"""
                SELECT COUNT(*) FROM documents
                WHERE indexed_at IS NOT NULL AND word_count < {ph} AND {indexed_filter}
                """,
                (80, cutoff_str),
            )
            short_count = int(cur.fetchone()[0] or 0)
            crawl_data["short_content_rate"] = _ratio_percent(
                short_count, indexed_count
            )

            if postgres_mode:
                cur.execute(
                    f"""
                    SELECT COUNT(*), COUNT(DISTINCT md5(content))
                    FROM documents
                    WHERE indexed_at IS NOT NULL
                      AND content IS NOT NULL
                      AND content <> ''
                      AND {indexed_filter}
                    """,
                    (cutoff_str,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT COUNT(*), COUNT(DISTINCT content)
                    FROM documents
                    WHERE indexed_at IS NOT NULL
                      AND content IS NOT NULL
                      AND content <> ''
                      AND {indexed_filter}
                    """,
                    (cutoff_str,),
                )
            total_with_content, unique_contents = cur.fetchone()
            total_with_content = int(total_with_content or 0)
            unique_contents = int(unique_contents or 0)
            duplicate_count = max(total_with_content - unique_contents, 0)
            crawl_data["duplicate_content_rate"] = _ratio_percent(
                duplicate_count, total_with_content
            )

        if _table_exists(conn, "urls"):
            cur.execute("SELECT COUNT(*) FROM urls WHERE status = 'pending'")
            crawl_data["pending_count"] = int(cur.fetchone()[0] or 0)

        if _table_exists(conn, "crawl_logs"):
            status_ph = sql_placeholders(len(CRAWL_ATTEMPT_STATUSES))
            cur.execute(
                f"""
                SELECT status, COUNT(*)
                FROM crawl_logs
                WHERE created_at >= {ph}
                  AND status IN ({status_ph})
                GROUP BY status
                """,
                (cutoff_epoch, *CRAWL_ATTEMPT_STATUSES),
            )
            status_counts = {status: int(count) for status, count in cur.fetchall()}
            attempts = sum(status_counts.values())
            success = status_counts.get("indexed", 0)
            crawl_data["crawl_success_rate"] = _ratio_percent(success, attempts)

        cur.close()
    finally:
        conn.close()

    return {
        "window": f"{window_hours}h",
        "cutoff_utc": cutoff_str,
        "search": search_data,
        "crawl": crawl_data,
    }


def _table_exists(conn: Any, table_name: str) -> bool:
    cur = conn.cursor()
    try:
        ph = sql_placeholder()
        if is_postgres_mode():
            cur.execute(
                f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = {ph}
                )
                """,
                (table_name,),
            )
            return bool(cur.fetchone()[0])

        cur.execute(
            f"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = {ph}",
            (table_name,),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()


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
