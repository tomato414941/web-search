from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.services.crawler_admin_client import get_crawler_instance_status


@pytest.mark.asyncio
async def test_get_crawler_instance_status_maps_extended_metrics():
    queue_resp = MagicMock()
    queue_resp.status_code = 200
    queue_resp.json.return_value = {"queue_size": 11, "active_seen": 22}

    worker_resp = MagicMock()
    worker_resp.status_code = 200
    worker_resp.json.return_value = {
        "status": "running",
        "uptime_seconds": 123.4,
        "concurrency": 4,
    }

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
        mock_instance.get.side_effect = [queue_resp, worker_resp, stats_resp]
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
    queue_resp = MagicMock()
    queue_resp.status_code = 200
    queue_resp.json.return_value = {"queue_size": 3, "active_seen": 9}

    worker_resp = MagicMock()
    worker_resp.status_code = 500
    worker_resp.json.return_value = {}

    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.json.return_value = {
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
        mock_instance.get.side_effect = [queue_resp, worker_resp, stats_resp]
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await get_crawler_instance_status("http://crawler:8000")

    assert result["state"] == "running"
    assert result["attempts_1h"] == 12
    assert result["indexed_1h"] == 6
    assert result["success_rate_1h"] == 50.0
    assert result["error_1h"] == 2
    assert result["uptime"] == 77.7
    assert result["concurrency"] == 2
