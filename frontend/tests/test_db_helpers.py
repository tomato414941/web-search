from frontend.services.db_helpers import db_cursor


class _FakeCursor:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_db_cursor_closes_resources_on_success(monkeypatch):
    conn = _FakeConnection()

    monkeypatch.setattr("frontend.services.db_helpers.get_connection", lambda _: conn)

    with db_cursor("/tmp/test.db") as (current_conn, cursor):
        assert current_conn is conn
        assert cursor is conn.cursor_obj

    assert conn.cursor_obj.closed is True
    assert conn.closed is True


def test_db_cursor_closes_resources_on_exception(monkeypatch):
    conn = _FakeConnection()

    monkeypatch.setattr("frontend.services.db_helpers.get_connection", lambda _: conn)

    try:
        with db_cursor("/tmp/test.db"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert conn.cursor_obj.closed is True
    assert conn.closed is True
