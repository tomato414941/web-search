from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.api.routers.admin import get_analytics_data, get_dashboard_data
from frontend.services import admin_dashboard
from shared.postgres.search import get_connection


def _insert_search_log(query: str, result_count: int, user_agent: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO search_logs (query, result_count, search_mode, user_agent)
        VALUES (%s, %s, %s, %s)
        """,
        (query, result_count, "bm25", user_agent),
    )
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(autouse=True)
def _set_exclusion_filters(monkeypatch):
    admin_dashboard._clear_dashboard_cache()
    monkeypatch.setattr(
        "frontend.services.admin_analytics.settings.ANALYTICS_EXCLUDED_USER_AGENTS",
        "curl/",
    )
    monkeypatch.setattr(
        "frontend.services.admin_analytics.settings.ANALYTICS_EXCLUDED_QUERIES",
        "deploy-check,bm25,sudachipy",
    )
    yield
    admin_dashboard._clear_dashboard_cache()


@pytest.mark.asyncio
async def test_dashboard_excludes_noise_queries_from_zero_hits():
    _insert_search_log("deploy-check", 0, "curl/8.5.0")
    _insert_search_log("bm25", 0, "curl/8.5.0")
    _insert_search_log("real-zero", 0, "Mozilla/5.0")
    _insert_search_log("real-hit", 3, "Mozilla/5.0")

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


@pytest.mark.asyncio
async def test_dashboard_uses_cache(monkeypatch):
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 123,
                "indexed_delta": 7,
                "last_crawl": "2026-03-06T00:00:00Z",
                "today_searches": 2,
                "today_unique_queries": 2,
                "today_zero_hits": 0,
                "zero_hit_rate": 0.0,
                "top_query": {"query": "cache", "count": 1},
                "zero_hit_queries": [],
            }
        ),
    )
    mock_fetch_stats = AsyncMock(
        return_value={
            "queue_size": 0,
            "active_seen": 0,
            "worker_status": "running",
            "uptime_seconds": 10,
            "active_tasks": 0,
            "crawl_rate_1h": 0,
            "error_count_1h": 0,
            "recent_errors": [],
        }
    )
    mock_fetch_breakdown = AsyncMock(return_value={"pending": 1})
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_stats", mock_fetch_stats
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_status_breakdown",
        mock_fetch_breakdown,
    )

    first = await admin_dashboard.get_dashboard_data()
    first["health"]["messages"].append("mutated")
    second = await admin_dashboard.get_dashboard_data()

    assert first["indexed_pages"] == 123
    assert second["indexed_pages"] == 123
    assert "mutated" not in second["health"]["messages"]
    assert (
        admin_dashboard._get_db_dashboard_data.call_count == 1  # type: ignore[attr-defined]
    )
    assert mock_fetch_stats.await_count == 1
    assert mock_fetch_breakdown.await_count == 1


def test_analytics_excludes_noise_queries():
    _insert_search_log("deploy-check", 0, "curl/8.5.0")
    _insert_search_log("real-zero", 0, "Mozilla/5.0")
    _insert_search_log("real-hit", 4, "Mozilla/5.0")

    data = get_analytics_data()

    assert data["total_searches"] == 2
    assert {"query": "deploy-check", "count": 1} not in data["zero_hit_queries"]
    assert data["zero_hit_queries"] == [{"query": "real-zero", "count": 1}]
