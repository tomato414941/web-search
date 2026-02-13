import logging
from typing import Any

from frontend.core.config import settings
from frontend.services.admin_analytics import (
    build_analytics_exclusion_filters,
    time_boundaries,
)
from frontend.services.crawler_admin_client import fetch_stats
from frontend.services.db_helpers import db_cursor
from shared.db.search import is_postgres_mode, sql_placeholder

logger = logging.getLogger(__name__)


async def get_dashboard_data() -> dict[str, Any]:
    data: dict[str, Any] = {
        "indexed_pages": 0,
        "indexed_delta": 0,
        "queue_size": 0,
        "visited_count": 0,
        "last_crawl": None,
        "worker_status": "unknown",
        "uptime_seconds": None,
        "active_tasks": 0,
        "recent_error_count": 0,
        "crawl_rate": 0,
        "today_searches": 0,
        "today_unique_queries": 0,
        "today_zero_hits": 0,
        "zero_hit_rate": 0.0,
        "top_query": None,
        "zero_hit_queries": [],
        "recent_errors": [],
        "health": {"level": "ok", "messages": []},
    }

    try:
        ph = sql_placeholder()
        is_postgres = is_postgres_mode()
        day_ago, _, today_start = time_boundaries()
        search_filter_sql, search_filter_params = build_analytics_exclusion_filters(
            is_postgres
        )
        with db_cursor(settings.DB_PATH) as (_, cursor):
            cursor.execute("SELECT COUNT(*) FROM documents")
            data["indexed_pages"] = cursor.fetchone()[0]

            if is_postgres:
                cursor.execute(
                    f"SELECT COUNT(*) FROM documents WHERE indexed_at >= {ph}",
                    (day_ago,),
                )
            else:
                cursor.execute(
                    f"SELECT COUNT(*) FROM documents WHERE datetime(indexed_at) >= datetime({ph})",
                    (day_ago,),
                )
            data["indexed_delta"] = cursor.fetchone()[0]

            cursor.execute(
                "SELECT MAX(indexed_at) FROM documents WHERE indexed_at IS NOT NULL"
            )
            result = cursor.fetchone()
            if result and result[0]:
                data["last_crawl"] = result[0]

            if is_postgres:
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT query) as unique_queries,
                        SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) as zero_hits
                    FROM search_logs
                    WHERE created_at >= {ph}{search_filter_sql}
                    """,
                    (today_start, *search_filter_params),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT query) as unique_queries,
                        SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) as zero_hits
                    FROM search_logs
                    WHERE datetime(created_at) >= datetime({ph}){search_filter_sql}
                    """,
                    (today_start, *search_filter_params),
                )
            row = cursor.fetchone()
            if row:
                data["today_searches"] = row[0] or 0
                data["today_unique_queries"] = row[1] or 0
                data["today_zero_hits"] = row[2] or 0
                if data["today_searches"] > 0:
                    data["zero_hit_rate"] = round(
                        data["today_zero_hits"] / data["today_searches"] * 100,
                        1,
                    )

            if is_postgres:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count
                    FROM search_logs
                    WHERE created_at >= {ph}{search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 1
                    """,
                    (today_start, *search_filter_params),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count
                    FROM search_logs
                    WHERE datetime(created_at) >= datetime({ph}){search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 1
                    """,
                    (today_start, *search_filter_params),
                )
            row = cursor.fetchone()
            if row and row[0]:
                data["top_query"] = {"query": row[0], "count": row[1]}

            if is_postgres:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count
                    FROM search_logs
                    WHERE result_count = 0 AND created_at >= {ph}{search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 5
                    """,
                    (today_start, *search_filter_params),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count
                    FROM search_logs
                    WHERE result_count = 0 AND datetime(created_at) >= datetime({ph}){search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 5
                    """,
                    (today_start, *search_filter_params),
                )
            data["zero_hit_queries"] = [
                {"query": row[0], "count": row[1]} for row in cursor.fetchall()
            ]
    except Exception as exc:
        logger.warning(f"Failed to get DB stats: {exc}")

    crawler_reachable = False
    stats = await fetch_stats()
    if stats:
        crawler_reachable = True
        data["queue_size"] = stats.get("queue_size", 0)
        data["visited_count"] = stats.get("active_seen", 0)
        data["worker_status"] = stats.get("worker_status", "unknown")
        data["uptime_seconds"] = stats.get("uptime_seconds")
        data["active_tasks"] = stats.get("active_tasks", 0)
        data["crawl_rate"] = stats.get("crawl_rate_1h", 0)
        data["recent_error_count"] = stats.get("error_count_1h", 0)
        data["recent_errors"] = stats.get("recent_errors", [])

    health_messages: list[str] = []
    if not crawler_reachable:
        health_messages.append("Crawler service is unreachable")
        data["health"]["level"] = "error"
    elif data["worker_status"] == "stopped":
        health_messages.append("Crawler is stopped. Indexing paused.")
        data["health"]["level"] = "warning"
    elif data["queue_size"] == 0 and data["worker_status"] == "running":
        health_messages.append("Queue is empty. Waiting for new URLs.")
        data["health"]["level"] = "warning"

    if data["zero_hit_rate"] > 50 and data["today_searches"] >= 10:
        health_messages.append(
            f"High zero-hit rate: {data['zero_hit_rate']}% of searches returned no results"
        )
        if data["health"]["level"] == "ok":
            data["health"]["level"] = "warning"

    data["health"]["messages"] = health_messages
    return data
