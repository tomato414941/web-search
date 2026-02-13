import pytest

from app.services.indexer import IndexerService


class _FakeCursor:
    def __init__(self):
        self.closed = False

    def execute(self, _sql, _params=None):
        return None

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self):
        self.closed = False
        self.commit_count = 0
        self.rollback_count = 0
        self._cursor = _FakeCursor()

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


class _DummyIndexer:
    def index_document(self, _url, _title, _content, _conn):
        return None

    def update_global_stats(self, _conn):
        return None


class _FailingIndexer:
    def index_document(self, _url, _title, _content, _conn):
        raise RuntimeError("index failed")

    def update_global_stats(self, _conn):
        return None


@pytest.mark.asyncio
async def test_index_page_closes_connection_on_success(monkeypatch):
    fake_conn = _FakeConnection()
    monkeypatch.setattr("app.services.indexer.get_connection", lambda _path: fake_conn)
    monkeypatch.setattr("app.services.indexer.settings.OPENAI_API_KEY", "")

    service = IndexerService("dummy.db")
    service.search_indexer = _DummyIndexer()

    await service.index_page(
        url="https://example.com",
        title="title",
        content="content",
        outlinks=None,
    )

    assert fake_conn.commit_count == 1
    assert fake_conn.rollback_count == 0
    assert fake_conn.closed is True


@pytest.mark.asyncio
async def test_index_page_rolls_back_and_closes_connection_on_failure(monkeypatch):
    fake_conn = _FakeConnection()
    monkeypatch.setattr("app.services.indexer.get_connection", lambda _path: fake_conn)
    monkeypatch.setattr("app.services.indexer.settings.OPENAI_API_KEY", "")

    service = IndexerService("dummy.db")
    service.search_indexer = _FailingIndexer()

    with pytest.raises(RuntimeError):
        await service.index_page(
            url="https://example.com",
            title="title",
            content="content",
            outlinks=None,
        )

    assert fake_conn.commit_count == 0
    assert fake_conn.rollback_count == 1
    assert fake_conn.closed is True
