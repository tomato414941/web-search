from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web_search_frontend.services import (
    crawler_admin_client as crawler_admin_client_module,
)
from web_search_frontend.services.crawler_admin_client import (
    clear_crawler_instances_cache,
    get_all_crawler_instances,
    get_crawler_instances_read_model,
    get_crawler_instance_status,
    prewarm_crawler_instances_cache,
)


@pytest.fixture(autouse=True)
def clear_crawler_instances_state():
    clear_crawler_instances_cache()
    yield
    clear_crawler_instances_cache()


@pytest.mark.asyncio
async def test_get_crawler_instance_status_maps_extended_metrics():
    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {
        "attempts_count_1h": 80,
        "submitted_count_1h": 40,
        "submit_rate_1h": 50.0,
        "error_count_1h": 5,
        "frontier_pending": 11,
        "active_seen": 22,
    }
    worker_resp = MagicMock()
    worker_resp.status_code = 200
    worker_resp.json.return_value = {
        "status": "running",
        "uptime_seconds": 123.4,
        "active_tasks": 3,
        "concurrency": 4,
    }

    with patch(
        "web_search_frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = [stats_resp, worker_resp]
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await get_crawler_instance_status("http://crawler:8000")

    assert result["state"] == "running"
    assert result["frontier_pending"] == 11
    assert result["active_seen"] == 22
    assert result["uptime"] == 123.4
    assert result["concurrency"] == 4
    assert result["attempts_1h"] == 80
    assert result["submitted_1h"] == 40
    assert result["submit_rate_1h"] == 50.0
    assert result["error_1h"] == 5


@pytest.mark.asyncio
async def test_get_crawler_instance_status_requires_current_stats_contract():
    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {
        "frontier_pending": 3,
        "active_seen": 9,
        "submitted_count_1h": 6,
        "submit_rate_1h": 50.0,
        "error_count_1h": 2,
    }
    worker_resp = MagicMock()
    worker_resp.status_code = 200
    worker_resp.json.return_value = {
        "status": "running",
        "concurrency": 2,
    }

    with patch(
        "web_search_frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = [stats_resp, worker_resp]
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await get_crawler_instance_status("http://crawler:8000")

    assert result["state"] == "running"
    assert result["attempts_1h"] is None
    assert result["submitted_1h"] == 6
    assert result["submit_rate_1h"] == 50.0
    assert result["error_1h"] == 2
    assert result["uptime"] is None
    assert result["concurrency"] == 2


@pytest.mark.asyncio
async def test_get_all_crawler_instances_uses_shared_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(
        crawler_admin_client_module,
        "_SHARED_CRAWLER_INSTANCES_CACHE_PATH",
        str(tmp_path / "crawler-instances-cache.json"),
    )
    clear_crawler_instances_cache()

    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {"frontier_pending": 5}
    worker_resp = MagicMock()
    worker_resp.status_code = 200
    worker_resp.json.return_value = {"status": "running"}

    with patch(
        "web_search_frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = [stats_resp, worker_resp]
        mock_client.return_value.__aenter__.return_value = mock_instance

        instances = [{"name": "default", "url": "http://crawler:8000"}]
        first = await get_all_crawler_instances(instances)
        crawler_admin_client_module._clear_crawler_instances_memory_cache()
        second = await get_all_crawler_instances(instances)

    assert mock_instance.get.await_count == 2
    assert first == second
    assert second[0]["state"] == "running"


@pytest.mark.asyncio
async def test_get_crawler_instances_read_model_exposes_snapshot_metadata(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        crawler_admin_client_module,
        "_SHARED_CRAWLER_INSTANCES_CACHE_PATH",
        str(tmp_path / "crawler-instances-cache.json"),
    )
    clear_crawler_instances_cache()

    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {"frontier_pending": 5}
    worker_resp = MagicMock()
    worker_resp.status_code = 200
    worker_resp.json.return_value = {"status": "running"}

    with patch(
        "web_search_frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = [stats_resp, worker_resp]
        mock_client.return_value.__aenter__.return_value = mock_instance

        instances = [{"name": "default", "url": "http://crawler:8000"}]
        first = await get_crawler_instances_read_model(instances)
        crawler_admin_client_module._clear_crawler_instances_memory_cache()
        second = await get_crawler_instances_read_model(instances)

    assert first["instances"][0]["state"] == "running"
    assert second["instances"][0]["state"] == "running"
    assert first["snapshot_generated_at"] == second["snapshot_generated_at"]
    assert first["snapshot_loaded_from"] == "live"
    assert second["snapshot_loaded_from"] == "shared"
    assert mock_instance.get.await_count == 2


@pytest.mark.asyncio
async def test_prewarm_crawler_instances_cache_populates_shared_cache(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        crawler_admin_client_module,
        "_SHARED_CRAWLER_INSTANCES_CACHE_PATH",
        str(tmp_path / "crawler-instances-cache.json"),
    )
    clear_crawler_instances_cache()

    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {"frontier_pending": 8}
    worker_resp = MagicMock()
    worker_resp.status_code = 200
    worker_resp.json.return_value = {"status": "running"}

    with patch(
        "web_search_frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = [stats_resp, worker_resp]
        mock_client.return_value.__aenter__.return_value = mock_instance

        instances = [{"name": "default", "url": "http://crawler:8000"}]
        await prewarm_crawler_instances_cache(instances, attempts=1, delay_seconds=0)
        crawler_admin_client_module._clear_crawler_instances_memory_cache()
        cached = await get_all_crawler_instances(instances)

    assert mock_instance.get.await_count == 2
    assert cached[0]["frontier_pending"] == 8
