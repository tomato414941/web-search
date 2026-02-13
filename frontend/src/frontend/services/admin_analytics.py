import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from frontend.core.config import settings
from frontend.services.db_helpers import db_cursor
from shared.db.search import is_postgres_mode, sql_placeholder, sql_placeholders

logger = logging.getLogger(__name__)


def time_boundaries() -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    today_start = now.strftime("%Y-%m-%d 00:00:00")
    return day_ago, week_ago, today_start


def build_analytics_exclusion_filters(is_postgres: bool) -> tuple[str, tuple[Any, ...]]:
    ph = sql_placeholder()
    clauses: list[str] = []
    params: list[Any] = []

    excluded_user_agents = settings.ANALYTICS_EXCLUDED_USER_AGENTS
    if excluded_user_agents:
        ua_clauses: list[str] = []
        for user_agent in excluded_user_agents:
            pattern = user_agent if "%" in user_agent else f"{user_agent}%"
            if is_postgres:
                ua_clauses.append(f"COALESCE(user_agent, '') ILIKE {ph}")
            else:
                ua_clauses.append(f"LOWER(COALESCE(user_agent, '')) LIKE LOWER({ph})")
            params.append(pattern)
        clauses.append("NOT (" + " OR ".join(ua_clauses) + ")")

    excluded_queries = settings.ANALYTICS_EXCLUDED_QUERIES
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
        ph = sql_placeholder()
        is_postgres = is_postgres_mode()
        _, week_ago, _ = time_boundaries()
        search_filter_sql, search_filter_params = build_analytics_exclusion_filters(
            is_postgres
        )
        with db_cursor(settings.DB_PATH) as (_, cursor):
            if is_postgres:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM search_logs
                    WHERE created_at >= {ph}{search_filter_sql}
                    """,
                    (week_ago, *search_filter_params),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM search_logs
                    WHERE datetime(created_at) >= datetime({ph}){search_filter_sql}
                    """,
                    (week_ago, *search_filter_params),
                )
            data["total_searches"] = cursor.fetchone()[0]

            if is_postgres:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count, AVG(result_count) as avg_results
                    FROM search_logs
                    WHERE created_at >= {ph}{search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 20
                    """,
                    (week_ago, *search_filter_params),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count, AVG(result_count) as avg_results
                    FROM search_logs
                    WHERE datetime(created_at) >= datetime({ph}){search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 20
                    """,
                    (week_ago, *search_filter_params),
                )
            data["top_queries"] = [
                {"query": row[0], "count": row[1], "avg_results": round(row[2], 1)}
                for row in cursor.fetchall()
            ]

            if is_postgres:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count
                    FROM search_logs
                    WHERE result_count = 0 AND created_at >= {ph}{search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 20
                    """,
                    (week_ago, *search_filter_params),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT query, COUNT(*) as count
                    FROM search_logs
                    WHERE result_count = 0 AND datetime(created_at) >= datetime({ph}){search_filter_sql}
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT 20
                    """,
                    (week_ago, *search_filter_params),
                )
            data["zero_hit_queries"] = [
                {"query": row[0], "count": row[1]} for row in cursor.fetchall()
            ]
    except Exception as exc:
        logger.warning(f"Failed to get analytics data: {exc}")

    return data
