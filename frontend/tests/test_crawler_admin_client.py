from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.services import crawler_admin_client as crawler_admin_client_module
from frontend.services.crawler_admin_client import (
    clear_crawler_instances_cache,
    fetch_seeds_page,
    get_all_crawler_instances,
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
        "indexed_count_1h": 40,
        "success_rate_1h": 50.0,
        "error_count_1h": 5,
        "queue_size": 11,
        "active_seen": 22,
        "worker_status": "running",
        "uptime_seconds": 123.4,
        "concurrency": 4,
    }

    with patch(
        "frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = stats_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await get_crawler_instance_status("http://crawler:8000")

    assert result["state"] == "running"
    assert result["queue_size"] == 11
    assert result["active_seen"] == 22
    assert result["uptime"] == 123.4
    assert result["concurrency"] == 4
    assert result["attempts_1h"] == 80
    assert result["indexed_1h"] == 40
    assert result["success_rate_1h"] == 50.0
    assert result["error_1h"] == 5


@pytest.mark.asyncio
async def test_get_crawler_instance_status_attempts_fallback_to_crawl_rate():
    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {
        "queue_size": 3,
        "active_seen": 9,
        "crawl_rate_1h": 12,
        "indexed_count_1h": 6,
        "success_rate_1h": 50.0,
        "error_count_1h": 2,
        "worker_status": "running",
        "uptime_seconds": 77.7,
        "concurrency": 2,
    }

    with patch(
        "frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = stats_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await get_crawler_instance_status("http://crawler:8000")

    assert result["state"] == "running"
    assert result["attempts_1h"] == 12
    assert result["indexed_1h"] == 6
    assert result["success_rate_1h"] == 50.0
    assert result["error_1h"] == 2
    assert result["uptime"] == 77.7
    assert result["concurrency"] == 2


@pytest.mark.asyncio
async def test_fetch_seeds_page_maps_paginated_response():
    seeds_resp = MagicMock()
    seeds_resp.status_code = 200
    seeds_resp.json.return_value = {
        "items": [
            {"url": "https://example.com", "status": "done"},
            {"url": "https://example.org", "status": "pending"},
        ],
        "total": 7,
        "limit": 2,
        "offset": 2,
    }

    with patch(
        "frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = seeds_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await fetch_seeds_page(page=2, per_page=2)

    assert result["items"][0]["url"] == "https://example.com"
    assert result["total"] == 7
    assert result["page"] == 2
    assert result["per_page"] == 2
    assert result["last_page"] == 4


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
    stats_resp.json.return_value = {"worker_status": "running", "queue_size": 5}

    with patch(
        "frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = stats_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        instances = [{"name": "default", "url": "http://crawler:8000"}]
        first = await get_all_crawler_instances(instances)
        crawler_admin_client_module._clear_crawler_instances_memory_cache()
        second = await get_all_crawler_instances(instances)

    assert mock_instance.get.await_count == 1
    assert first == second
    assert second[0]["state"] == "running"


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
    stats_resp.json.return_value = {"worker_status": "running", "queue_size": 8}

    with patch(
        "frontend.services.crawler_admin_client.httpx.AsyncClient"
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = stats_resp
        mock_client.return_value.__aenter__.return_value = mock_instance

        instances = [{"name": "default", "url": "http://crawler:8000"}]
        await prewarm_crawler_instances_cache(instances, attempts=1, delay_seconds=0)
        crawler_admin_client_module._clear_crawler_instances_memory_cache()
        cached = await get_all_crawler_instances(instances)

    assert mock_instance.get.await_count == 1
    assert cached[0]["queue_size"] == 8
