import time
from unittest.mock import AsyncMock, patch

import pytest

from web_search_frontend.services import (
    indexer_admin_client as indexer_admin_client_module,
)


@pytest.fixture(autouse=True)
def clear_indexer_admin_state(monkeypatch, tmp_path):
    monkeypatch.setattr(
        indexer_admin_client_module,
        "_SHARED_INDEXER_CACHE_PATH",
        str(tmp_path / "indexer-admin-cache.json"),
    )
    indexer_admin_client_module.clear_indexer_admin_cache()
    yield
    indexer_admin_client_module.clear_indexer_admin_cache()


@pytest.mark.asyncio
async def test_get_indexer_admin_read_model_uses_cache():
    health = {"reachable": True, "ok": True, "indexed_pages": 12}
    failed_jobs = [{"job_id": "job-1"}]

    with (
        patch(
            "web_search_frontend.services.indexer_admin_client.fetch_indexer_stats",
            new=AsyncMock(return_value=health),
        ) as mock_stats,
        patch(
            "web_search_frontend.services.indexer_admin_client.fetch_failed_jobs",
            new=AsyncMock(return_value=failed_jobs),
        ) as mock_failed,
    ):
        first = await indexer_admin_client_module.get_indexer_admin_read_model()
        second = await indexer_admin_client_module.get_indexer_admin_read_model()

    assert first["health"]["reachable"] is True
    assert first["health"]["ok"] is True
    assert first["health"]["indexed_pages"] == 12
    assert second["health"]["reachable"] is True
    assert second["health"]["ok"] is True
    assert second["health"]["indexed_pages"] == 12
    assert first["failed_jobs"][0]["job_id"] == "job-1"
    assert second["failed_jobs"][0]["job_id"] == "job-1"
    assert first["snapshot_generated_at"] == second["snapshot_generated_at"]
    assert first["snapshot_generated_at"] is not None
    assert first["snapshot_loaded_from"] == "live"
    assert second["snapshot_loaded_from"] == "memory"
    mock_stats.assert_awaited_once_with()
    mock_failed.assert_awaited_once_with(limit=50)


@pytest.mark.asyncio
async def test_prewarm_indexer_admin_cache_populates_cache():
    health = {"reachable": True, "ok": True, "indexed_pages": 12}
    failed_jobs = [{"job_id": "job-1"}]

    with (
        patch(
            "web_search_frontend.services.indexer_admin_client.fetch_indexer_stats",
            new=AsyncMock(return_value=health),
        ) as mock_stats,
        patch(
            "web_search_frontend.services.indexer_admin_client.fetch_failed_jobs",
            new=AsyncMock(return_value=failed_jobs),
        ) as mock_failed,
    ):
        await indexer_admin_client_module.prewarm_indexer_admin_cache(
            attempts=1, delay_seconds=0
        )
        indexer_admin_client_module._indexer_admin_cache.clear_memory()
        cached = await indexer_admin_client_module.get_indexer_admin_read_model()

    assert cached["health"]["reachable"] is True
    assert cached["health"]["ok"] is True
    assert cached["health"]["indexed_pages"] == 12
    assert cached["failed_jobs"][0]["job_id"] == "job-1"
    assert cached["snapshot_loaded_from"] == "shared"
    mock_stats.assert_awaited_once_with()
    mock_failed.assert_awaited_once_with(limit=50)


@pytest.mark.asyncio
async def test_retry_failed_job_clears_cached_read_model():
    with (
        patch(
            "web_search_frontend.services.indexer_admin_client.fetch_indexer_stats",
            new=AsyncMock(return_value={"reachable": True, "ok": True}),
        ),
        patch(
            "web_search_frontend.services.indexer_admin_client.fetch_failed_jobs",
            new=AsyncMock(return_value=[{"job_id": "job-1"}]),
        ),
    ):
        read_model = await indexer_admin_client_module.get_indexer_admin_read_model()

    assert read_model["failed_jobs"][0]["job_id"] == "job-1"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with (
        patch(
            "web_search_frontend.services.indexer_admin_client.settings.INDEXER_API_KEY",
            "test-key",
        ),
        patch(
            "web_search_frontend.services.indexer_admin_client.settings.INDEXER_SERVICE_URL",
            "http://indexer",
        ),
        patch(
            "web_search_frontend.services.indexer_admin_client.httpx.AsyncClient"
        ) as mock_async_client,
    ):
        mock_async_client.return_value.__aenter__.return_value = mock_client
        ok = await indexer_admin_client_module.retry_failed_job("job-1")

    assert ok is True
    assert (
        indexer_admin_client_module._get_memory_cached_indexer_admin_read_model(
            time.monotonic()
        )
        is None
    )
