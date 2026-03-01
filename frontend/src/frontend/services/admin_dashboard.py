import logging
from typing import Any

from frontend.core.config import settings
from frontend.services.admin_analytics import (
    build_analytics_exclusion_filters,
    time_boundaries,
)
from frontend.services.crawler_admin_client import fetch_stats, fetch_status_breakdown
from shared.postgres.search import get_connection
from shared.postgres.repositories.analytics_repo import AnalyticsRepository

logger = logging.getLogger(__name__)

_repo = AnalyticsRepository


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
        "status_breakdown": None,
        "health": {"level": "ok", "messages": []},
    }

    try:
        day_ago, _, today_start = time_boundaries()
        search_filter_sql, search_filter_params = build_analytics_exclusion_filters()
        conn = get_connection(settings.DB_PATH)
        try:
            data["indexed_pages"] = _repo.count_total_documents(conn)
            data["indexed_delta"] = _repo.count_indexed_since(conn, day_ago)
            data["last_crawl"] = _repo.max_indexed_at(conn)

            summary = _repo.today_summary(
                conn, today_start, search_filter_sql, search_filter_params
            )
            data["today_searches"] = summary["total"]
            data["today_unique_queries"] = summary["unique_queries"]
            data["today_zero_hits"] = summary["zero_hits"]
            if data["today_searches"] > 0:
                data["zero_hit_rate"] = round(
                    data["today_zero_hits"] / data["today_searches"] * 100,
                    1,
                )

            top = _repo.top_queries(
                conn, today_start, 1, search_filter_sql, search_filter_params
            )
            if top:
                data["top_query"] = {"query": top[0]["query"], "count": top[0]["count"]}

            data["zero_hit_queries"] = _repo.zero_hit_queries(
                conn, today_start, 5, search_filter_sql, search_filter_params
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Failed to get DB stats: {exc}")

    data["status_breakdown"] = await fetch_status_breakdown()

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
