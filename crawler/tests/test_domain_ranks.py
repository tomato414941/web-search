"""Tests for domain rank cache loading."""

from app.domain import domain_ranks


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, query):
        self.query = query

    def fetchall(self):
        return list(self._rows)

    def close(self):
        return None


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._rows)

    def close(self):
        self.closed = True


def test_load_domain_rank_cache_populates_entries(monkeypatch):
    fake_connection = _FakeConnection([("example.com", 0.5), ("docs.python.org", 0.8)])
    monkeypatch.setattr(domain_ranks, "get_connection", lambda _: fake_connection)

    domain_ranks.load_domain_rank_cache("unused")

    assert domain_ranks.domain_rank_cache_size() == 2


def test_load_domain_rank_cache_clears_cache_on_error(monkeypatch):
    fake_connection = _FakeConnection([("example.com", 0.5)])
    monkeypatch.setattr(domain_ranks, "get_connection", lambda _: fake_connection)
    domain_ranks.load_domain_rank_cache("unused")
    assert domain_ranks.domain_rank_cache_size() == 1

    def raise_error(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(domain_ranks, "get_connection", raise_error)
    domain_ranks.load_domain_rank_cache("unused")

    assert domain_ranks.domain_rank_cache_size() == 0


def test_load_domain_rank_cache_closes_connection(monkeypatch):
    fake_connection = _FakeConnection([("example.com", 0.5)])
    monkeypatch.setattr(domain_ranks, "get_connection", lambda _: fake_connection)

    domain_ranks.load_domain_rank_cache("unused")

    assert fake_connection.closed is True
