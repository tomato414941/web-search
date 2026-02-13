from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.api.routers.admin import get_analytics_data, get_dashboard_data
from frontend.core.config import settings
from shared.db.search import get_connection, is_postgres_mode


def _placeholder() -> str:
    return "%s" if is_postgres_mode() else "?"


def _insert_search_log(query: str, result_count: int, user_agent: str) -> None:
    ph = _placeholder()
    conn = get_connection(settings.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO search_logs (query, result_count, search_mode, user_agent)
        VALUES ({ph}, {ph}, {ph}, {ph})
        """,
        (query, result_count, "bm25", user_agent),
    )
    conn.commit()
    cur.close()
    conn.close()


@pytest.mark.asyncio
async def test_dashboard_excludes_noise_queries_from_zero_hits():
    _insert_search_log("deploy-check", 0, "curl/8.5.0")
    _insert_search_log("bm25", 0, "curl/8.5.0")
    _insert_search_log("real-zero", 0, "Mozilla/5.0")
    _insert_search_log("real-hit", 3, "Mozilla/5.0")

    with patch(
        "frontend.api.routers.admin.settings.ANALYTICS_EXCLUDED_USER_AGENTS",
        ["curl/"],
    ):
        with patch(
            "frontend.api.routers.admin.settings.ANALYTICS_EXCLUDED_QUERIES",
            ["deploy-check", "bm25", "sudachipy"],
        ):
            with patch(
                "frontend.services.crawler_admin_client.httpx.AsyncClient"
            ) as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "queue_size": 0,
                    "active_seen": 0,
                    "worker_status": "stopped",
                    "uptime_seconds": None,
                    "active_tasks": 0,
                    "crawl_rate_1h": 0,
                    "error_count_1h": 0,
                    "recent_errors": [],
                }
                mock_instance = AsyncMock()
                mock_instance.get.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_instance

                data = await get_dashboard_data()

    assert data["today_searches"] == 2
    assert data["today_zero_hits"] == 1
    assert data["zero_hit_rate"] == 50.0
    assert data["zero_hit_queries"] == [{"query": "real-zero", "count": 1}]


def test_analytics_excludes_noise_queries():
    _insert_search_log("deploy-check", 0, "curl/8.5.0")
    _insert_search_log("real-zero", 0, "Mozilla/5.0")
    _insert_search_log("real-hit", 4, "Mozilla/5.0")

    with patch(
        "frontend.api.routers.admin.settings.ANALYTICS_EXCLUDED_USER_AGENTS",
        ["curl/"],
    ):
        with patch(
            "frontend.api.routers.admin.settings.ANALYTICS_EXCLUDED_QUERIES",
            ["deploy-check", "bm25", "sudachipy"],
        ):
            data = get_analytics_data()

    assert data["total_searches"] == 2
    assert {"query": "deploy-check", "count": 1} not in data["zero_hit_queries"]
    assert data["zero_hit_queries"] == [{"query": "real-zero", "count": 1}]
