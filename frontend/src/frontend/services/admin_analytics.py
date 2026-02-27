import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from frontend.core.config import settings
from shared.db.search import get_connection, sql_placeholder, sql_placeholders
from shared.postgres.repositories.analytics_repo import AnalyticsRepository

logger = logging.getLogger(__name__)

_repo = AnalyticsRepository


def time_boundaries() -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    today_start = now.strftime("%Y-%m-%d 00:00:00")
    return day_ago, week_ago, today_start


def build_analytics_exclusion_filters() -> tuple[str, tuple[Any, ...]]:
    ph = sql_placeholder()
    clauses: list[str] = []
    params: list[Any] = []

    excluded_user_agents = settings.get_excluded_user_agents()
    if excluded_user_agents:
        ua_clauses: list[str] = []
        for user_agent in excluded_user_agents:
            pattern = user_agent if "%" in user_agent else f"{user_agent}%"
            ua_clauses.append(f"COALESCE(user_agent, '') ILIKE {ph}")
            params.append(pattern)
        clauses.append("NOT (" + " OR ".join(ua_clauses) + ")")

    excluded_queries = settings.get_excluded_queries()
    if excluded_queries:
        query_placeholders = sql_placeholders(len(excluded_queries))
        clauses.append(f"query NOT IN ({query_placeholders})")
        params.extend(excluded_queries)

    if not clauses:
        return "", tuple()

    return " AND " + " AND ".join(clauses), tuple(params)


def get_analytics_data() -> dict[str, Any]:
    data: dict[str, Any] = {
        "top_queries": [],
        "zero_hit_queries": [],
        "total_searches": 0,
    }

    try:
        _, week_ago, _ = time_boundaries()
        search_filter_sql, search_filter_params = build_analytics_exclusion_filters()
        conn = get_connection(settings.DB_PATH)
        try:
            data["total_searches"] = _repo.count_since(
                conn, week_ago, search_filter_sql, search_filter_params
            )
            data["top_queries"] = _repo.top_queries(
                conn, week_ago, 20, search_filter_sql, search_filter_params
            )
            data["zero_hit_queries"] = _repo.zero_hit_queries(
                conn, week_ago, 20, search_filter_sql, search_filter_params
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Failed to get analytics data: {exc}")

    return data
