import asyncio
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from web_search_frontend.metrics import (
    ADMIN_DASHBOARD_CACHE_ACCESS,
    ADMIN_DASHBOARD_PREWARM_LAST_SUCCESS,
    ADMIN_DASHBOARD_PREWARM_TOTAL,
)
from web_search_frontend.services import admin_dashboard
from web_search_core import background as background_module


def _metric_value(metric, sample_name: str, **labels: str) -> float:
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == sample_name and sample.labels == labels:
                return float(sample.value)
    return 0.0


@pytest.fixture(autouse=True)
def _clear_dashboard_cache():
    admin_dashboard._clear_dashboard_cache()
    yield
    admin_dashboard._clear_dashboard_cache()


@pytest.mark.asyncio
async def test_dashboard_uses_cache(monkeypatch):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 123,
                "indexed_delta": 7,
                "last_crawl": "2026-03-06T00:00:00Z",
            }
        ),
    )
    mock_fetch_stats = AsyncMock(
        return_value={
            "frontier_pending": 0,
            "worker_status": "running",
            "uptime_seconds": 10,
            "active_tasks": 0,
            "crawl_rate_1h": 0,
            "error_count_1h": 0,
            "recent_errors": [],
        }
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        mock_fetch_stats,
    )

    first = await admin_dashboard.get_dashboard_data()
    first["health"]["messages"].append("mutated")
    second = await admin_dashboard.get_dashboard_data()

    assert first["indexed_pages"] == 123
    assert second["indexed_pages"] == 123
    assert first["snapshot_generated_at"] == second["snapshot_generated_at"]
    assert first["snapshot_loaded_from"] == "live"
    assert second["snapshot_loaded_from"] == "memory"
    assert "mutated" not in second["health"]["messages"]
    assert (
        admin_dashboard._get_db_dashboard_data.call_count == 1  # type: ignore[attr-defined]
    )
    assert mock_fetch_stats.await_count == 1


@pytest.mark.asyncio
async def test_dashboard_uses_worker_active_tasks(monkeypatch):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        0,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(return_value={"indexed_pages": 1}),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        AsyncMock(
            return_value={
                "frontier_pending": 9,
                "worker_status": "running",
                "uptime_seconds": 10,
                "active_tasks": 2,
                "leased_tasks": 4,
                "crawl_rate_1h": 0,
                "error_count_1h": 0,
                "recent_errors": [],
            }
        ),
    )

    data = await admin_dashboard.get_dashboard_data()

    assert data["frontier_pending"] == 9
    assert data["active_tasks"] == 2


@pytest.mark.asyncio
async def test_dashboard_records_cache_access_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._SHARED_CACHE_PATH",
        str(tmp_path / "admin-dashboard-cache.json"),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 111,
                "indexed_delta": 2,
                "last_crawl": "2026-03-07T00:00:00Z",
            }
        ),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        AsyncMock(
            return_value={
                "frontier_pending": 0,
                "worker_status": "running",
                "uptime_seconds": 1,
                "active_tasks": 0,
                "crawl_rate_1h": 0,
                "error_count_1h": 0,
                "recent_errors": [],
            }
        ),
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
        "web_search_frontend.services.admin_dashboard._SHARED_CACHE_PATH",
        str(tmp_path / "admin-dashboard-cache.json"),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 456,
                "indexed_delta": 11,
                "last_crawl": "2026-03-07T00:00:00Z",
            }
        ),
    )
    mock_fetch_stats = AsyncMock(
        return_value={
            "frontier_pending": 1,
            "worker_status": "running",
            "uptime_seconds": 10,
            "active_tasks": 0,
            "crawl_rate_1h": 0,
            "error_count_1h": 0,
            "recent_errors": [],
        }
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        mock_fetch_stats,
    )

    first = await admin_dashboard.get_dashboard_data()
    admin_dashboard._clear_dashboard_memory_cache()
    second = await admin_dashboard.get_dashboard_data()

    assert first["indexed_pages"] == 456
    assert second["indexed_pages"] == 456
    assert first["snapshot_generated_at"] == second["snapshot_generated_at"]
    assert second["snapshot_loaded_from"] == "shared"
    assert admin_dashboard._get_db_dashboard_data.call_count == 1  # type: ignore[attr-defined]
    assert mock_fetch_stats.await_count == 1


@pytest.mark.asyncio
async def test_dashboard_singleflights_concurrent_cache_misses(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._SHARED_CACHE_PATH",
        str(tmp_path / "admin-dashboard-cache.json"),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 654,
                "indexed_delta": 12,
                "last_crawl": "2026-03-21T00:00:00Z",
            }
        ),
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_fetch_stats():
        started.set()
        await release.wait()
        return {
            "frontier_pending": 1,
            "worker_status": "running",
            "uptime_seconds": 10,
            "active_tasks": 0,
            "crawl_rate_1h": 0,
            "error_count_1h": 0,
            "recent_errors": [],
        }

    mock_fetch_stats = AsyncMock(side_effect=slow_fetch_stats)
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        mock_fetch_stats,
    )

    first_task = asyncio.create_task(admin_dashboard.get_dashboard_data())
    await started.wait()
    second_task = asyncio.create_task(admin_dashboard.get_dashboard_data())
    await asyncio.sleep(0)
    release.set()

    first, second = await asyncio.gather(first_task, second_task)

    assert first["indexed_pages"] == 654
    assert second["indexed_pages"] == 654
    assert admin_dashboard._get_db_dashboard_data.call_count == 1  # type: ignore[attr-defined]
    assert mock_fetch_stats.await_count == 1


@pytest.mark.asyncio
async def test_dashboard_rechecks_cache_after_singleflight_wait(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._SHARED_CACHE_PATH",
        str(tmp_path / "admin-dashboard-cache.json"),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(return_value={"indexed_pages": 999}),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        AsyncMock(return_value={"worker_status": "running"}),
    )

    @asynccontextmanager
    async def fake_singleflight():
        admin_dashboard._set_cached_dashboard_data(
            {
                "indexed_pages": 777,
                "indexed_delta": 0,
                "frontier_pending": 0,
                "last_crawl": None,
                "worker_status": "running",
                "uptime_seconds": 1,
                "active_tasks": 0,
                "recent_error_count": 0,
                "recent_errors": [],
                "health": {"level": "ok", "messages": []},
            }
        )
        yield

    monkeypatch.setattr(
        admin_dashboard, "_dashboard_build_singleflight", fake_singleflight
    )

    data = await admin_dashboard.get_dashboard_data()

    assert data["indexed_pages"] == 777
    assert admin_dashboard._get_db_dashboard_data.call_count == 0  # type: ignore[attr-defined]
    assert admin_dashboard.fetch_admin_stats.await_count == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_prewarm_dashboard_cache_populates_cache(monkeypatch):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 321,
                "indexed_delta": 8,
                "last_crawl": "2026-03-07T00:00:00Z",
            }
        ),
    )
    mock_fetch_stats = AsyncMock(
        return_value={
            "frontier_pending": 1,
            "worker_status": "stopped",
            "uptime_seconds": 10,
            "active_tasks": 0,
            "crawl_rate_1h": 0,
            "error_count_1h": 0,
            "recent_errors": [],
        }
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        mock_fetch_stats,
    )

    await admin_dashboard.prewarm_dashboard_cache(attempts=1, delay_seconds=0)
    cached = admin_dashboard._get_cached_dashboard_data(time.monotonic())

    assert cached is not None
    assert cached["indexed_pages"] == 321
    assert mock_fetch_stats.await_count == 1


@pytest.mark.asyncio
async def test_prewarm_dashboard_cache_records_metrics(monkeypatch):
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(
            return_value={
                "indexed_pages": 20,
                "indexed_delta": 1,
                "last_crawl": "2026-03-07T00:00:00Z",
            }
        ),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
        AsyncMock(
            return_value={
                "frontier_pending": 0,
                "worker_status": "running",
                "uptime_seconds": 5,
                "active_tasks": 0,
                "crawl_rate_1h": 0,
                "error_count_1h": 0,
                "recent_errors": [],
            }
        ),
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
        "web_search_frontend.services.admin_dashboard.settings.ADMIN_DASHBOARD_CACHE_TTL_SEC",
        30,
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard._get_db_dashboard_data",
        MagicMock(return_value={"indexed_pages": 10, "indexed_delta": 1}),
    )
    monkeypatch.setattr(
        "web_search_frontend.services.admin_dashboard.fetch_admin_stats",
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
