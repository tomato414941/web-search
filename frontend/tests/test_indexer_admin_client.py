from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frontend.services.indexer_admin_client import fetch_indexer_stats


@pytest.mark.asyncio
async def test_fetch_indexer_stats_uses_configured_timeout():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "indexed_pages": 123,
        "pending_jobs": 4,
        "processing_jobs": 2,
        "done_jobs": 90,
        "failed_permanent_jobs": 1,
        "total_jobs": 97,
        "oldest_pending_seconds": 33,
    }

    with (
        patch(
            "frontend.services.indexer_admin_client.settings.INDEXER_API_KEY",
            "test-key",
        ),
        patch(
            "frontend.services.indexer_admin_client.settings.INDEXER_SERVICE_URL",
            "http://indexer:8000",
        ),
        patch(
            "frontend.services.indexer_admin_client.settings.INDEXER_ADMIN_TIMEOUT_SEC",
            9.5,
        ),
        patch(
            "frontend.services.indexer_admin_client.httpx.AsyncClient"
        ) as mock_client,
    ):
        mock_instance = AsyncMock()
        mock_instance.get.return_value = response
        mock_client.return_value.__aenter__.return_value = mock_instance

        result = await fetch_indexer_stats()

    mock_client.assert_called_once_with(timeout=9.5)
    assert result["reachable"] is True
    assert result["ok"] is True
    assert result["indexed_pages"] == 123
    assert result["pending_jobs"] == 4
    assert result["processing_jobs"] == 2
    assert result["done_jobs"] == 90
    assert result["failed_permanent_jobs"] == 1
    assert result["total_jobs"] == 97
    assert result["oldest_pending_seconds"] == 33
