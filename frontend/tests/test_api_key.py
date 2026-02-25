"""Tests for API key authentication."""

import sqlite3

import pytest
from unittest.mock import patch

from frontend.services.api_key import (
    KEY_PREFIX,
    create_api_key,
    generate_key,
    get_daily_usage,
    list_api_keys,
    revoke_api_key,
    validate_api_key,
)


API_KEYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL UNIQUE,
  key_prefix TEXT NOT NULL,
  name TEXT NOT NULL,
  rate_limit_daily INTEGER NOT NULL DEFAULT 1000,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  last_used_at TEXT
);
"""

SEARCH_LOGS_API_KEY_COL = """
ALTER TABLE search_logs ADD COLUMN api_key_id TEXT;
"""


@pytest.fixture
def api_db(tmp_path):
    """Create a test database with api_keys table."""
    db_path = str(tmp_path / "api_test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(API_KEYS_SCHEMA)
    # Ensure search_logs exists for usage tracking
    conn.execute(
        """CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            result_count INTEGER DEFAULT 0,
            search_mode TEXT DEFAULT 'bm25',
            user_agent TEXT,
            api_key_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    conn.close()
    return db_path


class TestGenerateKey:
    def test_key_has_prefix(self):
        raw_key, key_hash, key_prefix = generate_key()
        assert raw_key.startswith(KEY_PREFIX)

    def test_key_prefix_matches(self):
        raw_key, key_hash, key_prefix = generate_key()
        assert raw_key[:12] == key_prefix

    def test_key_hash_is_hex(self):
        raw_key, key_hash, key_prefix = generate_key()
        assert len(key_hash) == 64
        int(key_hash, 16)  # Should not raise

    def test_keys_are_unique(self):
        keys = {generate_key()[0] for _ in range(10)}
        assert len(keys) == 10


class TestCreateAndValidate:
    def test_create_returns_raw_key(self, api_db):
        result = create_api_key("test-app", db_path=api_db)
        assert "raw_key" in result
        assert result["raw_key"].startswith(KEY_PREFIX)
        assert result["name"] == "test-app"

    def test_validate_returns_key_info(self, api_db):
        result = create_api_key("test-app", db_path=api_db)
        info = validate_api_key(result["raw_key"], db_path=api_db)
        assert info is not None
        assert info["id"] == result["id"]
        assert info["name"] == "test-app"
        assert info["rate_limit_daily"] == 1000

    def test_validate_invalid_key(self, api_db):
        assert validate_api_key("pbs_invalid_key_here", db_path=api_db) is None

    def test_validate_no_prefix(self, api_db):
        assert validate_api_key("no_prefix_key", db_path=api_db) is None

    def test_validate_empty(self, api_db):
        assert validate_api_key("", db_path=api_db) is None


class TestRevoke:
    def test_revoke_makes_key_invalid(self, api_db):
        result = create_api_key("test-app", db_path=api_db)
        assert revoke_api_key(result["id"], db_path=api_db) is True
        assert validate_api_key(result["raw_key"], db_path=api_db) is None

    def test_revoke_nonexistent_returns_false(self, api_db):
        assert revoke_api_key("nonexistent-id", db_path=api_db) is False

    def test_double_revoke_returns_false(self, api_db):
        result = create_api_key("test-app", db_path=api_db)
        assert revoke_api_key(result["id"], db_path=api_db) is True
        assert revoke_api_key(result["id"], db_path=api_db) is False


class TestListKeys:
    def test_list_returns_all_keys(self, api_db):
        create_api_key("app-1", db_path=api_db)
        create_api_key("app-2", db_path=api_db)
        keys = list_api_keys(db_path=api_db)
        assert len(keys) == 2
        names = {k["name"] for k in keys}
        assert names == {"app-1", "app-2"}

    def test_list_does_not_expose_hash(self, api_db):
        create_api_key("app-1", db_path=api_db)
        keys = list_api_keys(db_path=api_db)
        for key in keys:
            assert "key_hash" not in key
            assert "raw_key" not in key


class TestDailyUsage:
    def test_zero_usage_by_default(self, api_db):
        result = create_api_key("test-app", db_path=api_db)
        assert get_daily_usage(result["id"], db_path=api_db) == 0

    def test_counts_todays_logs(self, api_db):
        result = create_api_key("test-app", db_path=api_db)
        conn = sqlite3.connect(api_db)
        for _ in range(5):
            conn.execute(
                "INSERT INTO search_logs (query, result_count, api_key_id) VALUES (?, ?, ?)",
                ("test", 10, result["id"]),
            )
        conn.commit()
        conn.close()
        assert get_daily_usage(result["id"], db_path=api_db) == 5


class TestAPISearchWithKey:
    def test_search_without_key_succeeds(self):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/search", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" not in data

    def test_search_with_invalid_key_returns_401(self):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        with patch("frontend.api.deps.validate_api_key", return_value=None):
            client = TestClient(app)
            resp = client.get(
                "/api/v1/search",
                params={"q": "test"},
                headers={"X-API-Key": "pbs_invalid_key"},
            )
            assert resp.status_code == 401

    def test_search_with_valid_key_returns_usage(self, api_db):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        key_info = create_api_key("test-app", db_path=api_db)

        with patch("frontend.api.deps.validate_api_key") as mock_validate:
            mock_validate.return_value = {
                "id": key_info["id"],
                "key_prefix": key_info["key_prefix"],
                "name": "test-app",
                "rate_limit_daily": 1000,
            }
            with patch("frontend.api.deps.get_daily_usage", return_value=5):
                client = TestClient(app)
                resp = client.get(
                    "/api/v1/search",
                    params={"q": "test"},
                    headers={"X-API-Key": key_info["raw_key"]},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "usage" in data
                assert data["usage"]["daily_used"] == 6
                assert data["usage"]["daily_limit"] == 1000

    def test_search_with_key_via_query_param(self, api_db):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        with patch("frontend.api.deps.validate_api_key") as mock_validate:
            mock_validate.return_value = {
                "id": "test-id",
                "key_prefix": "pbs_test1234",
                "name": "test-app",
                "rate_limit_daily": 1000,
            }
            with patch("frontend.api.deps.get_daily_usage", return_value=0):
                client = TestClient(app)
                resp = client.get(
                    "/api/v1/search",
                    params={"q": "test", "api_key": "pbs_somekey"},
                )
                assert resp.status_code == 200
                assert "usage" in resp.json()
