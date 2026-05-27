import pytest

from web_search_frontend.services import indexer_admin_client


class _FakeResponse:
    status_code = 200

    def json(self):
        return {
            "ok": True,
            "indexed_pages": 12,
            "pending_jobs": 3,
            "processing_jobs": 1,
            "failed_permanent_jobs": 2,
        }


class _FakeAsyncClient:
    def __init__(self, *, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, *, headers):
        assert url == "http://indexer:8000/api/v1/indexer/stats"
        assert headers == {"X-API-Key": "secret"}
        return _FakeResponse()


@pytest.mark.asyncio
async def test_fetch_indexer_stats_returns_health_model(monkeypatch):
    monkeypatch.setattr(indexer_admin_client.settings, "INDEXER_API_KEY", "secret")
    monkeypatch.setattr(
        indexer_admin_client.settings,
        "INDEXER_SERVICE_URL",
        "http://indexer:8000",
    )
    monkeypatch.setattr(indexer_admin_client.httpx, "AsyncClient", _FakeAsyncClient)

    stats = await indexer_admin_client.fetch_indexer_stats()

    assert stats["reachable"] is True
    assert stats["ok"] is True
    assert stats["indexed_pages"] == 12
    assert stats["failed_permanent_jobs"] == 2


@pytest.mark.asyncio
async def test_fetch_indexer_stats_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr(indexer_admin_client.settings, "INDEXER_API_KEY", "")

    stats = await indexer_admin_client.fetch_indexer_stats()

    assert stats["reachable"] is False
    assert stats["error"] == "missing INDEXER_API_KEY"
