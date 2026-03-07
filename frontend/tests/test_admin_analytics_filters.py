import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.api.metrics import (
    ADMIN_DASHBOARD_CACHE_ACCESS,
    ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS,
    ADMIN_DASHBOARD_PREWARM_TOTAL,
)
from frontend.services import admin_dashboard
from frontend.services.admin_analytics import get_analytics_data
from frontend.services.admin_dashboard import get_dashboard_data
from shared.core import background as background_module
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


def _metric_value(metric, sample_name: str, **labels: str) -> float:
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == sample_name and sample.labels == labels:
                return float(sample.value)
    return 0.0


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


@pytest.mark.asyncio
async def test_dashboard_records_cache_access_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._SHARED_CACHE_PATH",
        str(tmp_path / "admin-dashboard-cache.json"),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 111,
                "indexed_delta": 2,
                "last_crawl": "2026-03-07T00:00:00Z",
                "today_searches": 1,
                "today_unique_queries": 1,
                "today_zero_hits": 0,
                "zero_hit_rate": 0.0,
                "top_query": {"query": "metrics", "count": 1},
                "zero_hit_queries": [],
            }
        ),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_stats",
        AsyncMock(
            return_value={
                "queue_size": 0,
                "active_seen": 0,
                "worker_status": "running",
                "uptime_seconds": 1,
                "active_tasks": 0,
                "crawl_rate_1h": 0,
                "error_count_1h": 0,
                "recent_errors": [],
            }
        ),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_status_breakdown",
        AsyncMock(return_value={"pending": 1}),
    )

    miss_before = _metric_value(
        ADMIN_DASHBOARD_CACHE_ACCESS,
        "admin_dashboard_cache_access_total",
        result="miss",
    )
    memory_before = _metric_value(
        ADMIN_DASHBOARD_CACHE_ACCESS,
        "admin_dashboard_cache_access_total",
        result="memory",
    )
    shared_before = _metric_value(
        ADMIN_DASHBOARD_CACHE_ACCESS,
        "admin_dashboard_cache_access_total",
        result="shared",
    )

    await admin_dashboard.get_dashboard_data()
    await admin_dashboard.get_dashboard_data()
    admin_dashboard._clear_dashboard_memory_cache()
    await admin_dashboard.get_dashboard_data()

    assert (
        _metric_value(
            ADMIN_DASHBOARD_CACHE_ACCESS,
            "admin_dashboard_cache_access_total",
            result="miss",
        )
        == miss_before + 1
    )
    assert (
        _metric_value(
            ADMIN_DASHBOARD_CACHE_ACCESS,
            "admin_dashboard_cache_access_total",
            result="memory",
        )
        == memory_before + 1
    )
    assert (
        _metric_value(
            ADMIN_DASHBOARD_CACHE_ACCESS,
            "admin_dashboard_cache_access_total",
            result="shared",
        )
        == shared_before + 1
    )


@pytest.mark.asyncio
async def test_dashboard_uses_shared_file_cache_across_workers(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._SHARED_CACHE_PATH",
        str(tmp_path / "admin-dashboard-cache.json"),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 456,
                "indexed_delta": 11,
                "last_crawl": "2026-03-07T00:00:00Z",
                "today_searches": 3,
                "today_unique_queries": 3,
                "today_zero_hits": 1,
                "zero_hit_rate": 33.3,
                "top_query": {"query": "shared", "count": 2},
                "zero_hit_queries": [{"query": "miss", "count": 1}],
            }
        ),
    )
    mock_fetch_stats = AsyncMock(
        return_value={
            "queue_size": 1,
            "active_seen": 2,
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
    admin_dashboard._clear_dashboard_memory_cache()
    second = await admin_dashboard.get_dashboard_data()

    assert first["indexed_pages"] == 456
    assert second["indexed_pages"] == 456
    assert admin_dashboard._get_db_dashboard_data.call_count == 1  # type: ignore[attr-defined]
    assert mock_fetch_stats.await_count == 1
    assert mock_fetch_breakdown.await_count == 1


@pytest.mark.asyncio
async def test_prewarm_dashboard_cache_populates_cache(monkeypatch):
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 321,
                "indexed_delta": 8,
                "last_crawl": "2026-03-07T00:00:00Z",
                "today_searches": 4,
                "today_unique_queries": 4,
                "today_zero_hits": 1,
                "zero_hit_rate": 25.0,
                "top_query": {"query": "prewarm", "count": 2},
                "zero_hit_queries": [{"query": "miss", "count": 1}],
            }
        ),
    )
    mock_fetch_stats = AsyncMock(
        return_value={
            "queue_size": 1,
            "active_seen": 2,
            "worker_status": "stopped",
            "uptime_seconds": 10,
            "active_tasks": 0,
            "crawl_rate_1h": 0,
            "error_count_1h": 0,
            "recent_errors": [],
        }
    )
    mock_fetch_breakdown = AsyncMock(return_value={"indexed": 1})
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_stats", mock_fetch_stats
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_status_breakdown",
        mock_fetch_breakdown,
    )

    await admin_dashboard.prewarm_dashboard_cache(attempts=1, delay_seconds=0)
    cached = admin_dashboard._get_cached_dashboard_data(time.monotonic())

    assert cached is not None
    assert cached["indexed_pages"] == 321
    assert cached["status_breakdown"] == {"indexed": 1}
    assert mock_fetch_stats.await_count == 1
    assert mock_fetch_breakdown.await_count == 1


@pytest.mark.asyncio
async def test_prewarm_dashboard_cache_records_metrics(monkeypatch):
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 20,
                "indexed_delta": 1,
                "last_crawl": "2026-03-07T00:00:00Z",
                "today_searches": 0,
                "today_unique_queries": 0,
                "today_zero_hits": 0,
                "zero_hit_rate": 0.0,
                "top_query": None,
                "zero_hit_queries": [],
            }
        ),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_stats",
        AsyncMock(
            return_value={
                "queue_size": 0,
                "active_seen": 0,
                "worker_status": "running",
                "uptime_seconds": 5,
                "active_tasks": 0,
                "crawl_rate_1h": 0,
                "error_count_1h": 0,
                "recent_errors": [],
            }
        ),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_status_breakdown",
        AsyncMock(return_value={"pending": 1}),
    )

    success_before = _metric_value(
        ADMIN_DASHBOARD_PREWARM_TOTAL,
        "admin_dashboard_prewarm_total",
        result="success",
    )
    last_success_before = _metric_value(
        ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS,
        "admin_dashboard_prewarm_last_success_timestamp_seconds",
    )

    await admin_dashboard.prewarm_dashboard_cache(attempts=1, delay_seconds=0)

    assert (
        _metric_value(
            ADMIN_DASHBOARD_PREWARM_TOTAL,
            "admin_dashboard_prewarm_total",
            result="success",
        )
        == success_before + 1
    )
    assert (
        _metric_value(
            ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS,
            "admin_dashboard_prewarm_last_success_timestamp_seconds",
        )
        >= last_success_before
    )


@pytest.mark.asyncio
async def test_prewarm_dashboard_cache_skips_unreachable_crawler(monkeypatch):
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(return_value={"indexed_pages": 10, "indexed_delta": 1}),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_stats",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "frontend.services.admin_dashboard.fetch_status_breakdown",
        AsyncMock(return_value=None),
    )

    await admin_dashboard.prewarm_dashboard_cache(attempts=1, delay_seconds=0)

    assert admin_dashboard._get_cached_dashboard_data(time.monotonic()) is None


@pytest.mark.asyncio
async def test_maintain_dashboard_cache_refreshes_periodically(monkeypatch):
    calls: list[tuple[int, float]] = []

    async def fake_prewarm(*, attempts: int = 60, delay_seconds: float = 5.0) -> None:
        calls.append((attempts, delay_seconds))
        if len(calls) >= 2:
            raise asyncio.CancelledError

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(admin_dashboard, "prewarm_dashboard_cache", fake_prewarm)
    monkeypatch.setattr(background_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await admin_dashboard.maintain_dashboard_cache(refresh_interval_seconds=15)

    assert calls == [(60, 5.0), (1, 0)]


def test_analytics_excludes_noise_queries():
    _insert_search_log("deploy-check", 0, "curl/8.5.0")
    _insert_search_log("real-zero", 0, "Mozilla/5.0")
    _insert_search_log("real-hit", 4, "Mozilla/5.0")

    data = get_analytics_data()

    assert data["total_searches"] == 2
    assert {"query": "deploy-check", "count": 1} not in data["zero_hit_queries"]
    assert data["zero_hit_queries"] == [{"query": "real-zero", "count": 1}]
