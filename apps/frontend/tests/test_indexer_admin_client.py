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

    with patch(
        "web_search_frontend.services.indexer_admin_client.fetch_indexer_stats",
        new=AsyncMock(return_value=health),
    ) as mock_stats:
        first = await indexer_admin_client_module.get_indexer_admin_read_model()
        second = await indexer_admin_client_module.get_indexer_admin_read_model()

    assert first["health"]["reachable"] is True
    assert first["health"]["ok"] is True
    assert first["health"]["indexed_pages"] == 12
    assert second["health"]["reachable"] is True
    assert second["health"]["ok"] is True
    assert second["health"]["indexed_pages"] == 12
    assert first["snapshot_generated_at"] == second["snapshot_generated_at"]
    assert first["snapshot_generated_at"] is not None
    assert first["snapshot_loaded_from"] == "live"
    assert second["snapshot_loaded_from"] == "memory"
    mock_stats.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_prewarm_indexer_admin_cache_populates_cache():
    health = {"reachable": True, "ok": True, "indexed_pages": 12}

    with patch(
        "web_search_frontend.services.indexer_admin_client.fetch_indexer_stats",
        new=AsyncMock(return_value=health),
    ) as mock_stats:
        await indexer_admin_client_module.prewarm_indexer_admin_cache(
            attempts=1, delay_seconds=0
        )
        indexer_admin_client_module._indexer_admin_cache.clear_memory()
        cached = await indexer_admin_client_module.get_indexer_admin_read_model()

    assert cached["health"]["reachable"] is True
    assert cached["health"]["ok"] is True
    assert cached["health"]["indexed_pages"] == 12
    assert cached["snapshot_loaded_from"] == "shared"
    mock_stats.assert_awaited_once_with()
