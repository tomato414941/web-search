"""Tests for API key authentication."""

from unittest.mock import patch

from shared.db.search import get_connection

from frontend.services.api_key import (
    KEY_PREFIX,
    create_api_key,
    generate_key,
    get_daily_usage,
    list_api_keys,
    revoke_api_key,
    validate_api_key,
)


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
    def test_create_returns_raw_key(self):
        result = create_api_key("test-app")
        assert "raw_key" in result
        assert result["raw_key"].startswith(KEY_PREFIX)
        assert result["name"] == "test-app"

    def test_validate_returns_key_info(self):
        result = create_api_key("test-app")
        info = validate_api_key(result["raw_key"])
        assert info is not None
        assert info["id"] == result["id"]
        assert info["name"] == "test-app"
        assert info["rate_limit_daily"] == 1000

    def test_validate_invalid_key(self):
        assert validate_api_key("pbs_invalid_key_here") is None

    def test_validate_no_prefix(self):
        assert validate_api_key("no_prefix_key") is None

    def test_validate_empty(self):
        assert validate_api_key("") is None


class TestRevoke:
    def test_revoke_makes_key_invalid(self):
        result = create_api_key("test-app")
        assert revoke_api_key(result["id"]) is True
        assert validate_api_key(result["raw_key"]) is None

    def test_revoke_nonexistent_returns_false(self):
        assert revoke_api_key("nonexistent-id") is False

    def test_double_revoke_returns_false(self):
        result = create_api_key("test-app")
        assert revoke_api_key(result["id"]) is True
        assert revoke_api_key(result["id"]) is False


class TestListKeys:
    def test_list_returns_all_keys(self):
        create_api_key("app-1")
        create_api_key("app-2")
        keys = list_api_keys()
        assert len(keys) == 2
        names = {k["name"] for k in keys}
        assert names == {"app-1", "app-2"}

    def test_list_does_not_expose_hash(self):
        create_api_key("app-1")
        keys = list_api_keys()
        for key in keys:
            assert "key_hash" not in key
            assert "raw_key" not in key


class TestDailyUsage:
    def test_zero_usage_by_default(self):
        result = create_api_key("test-app")
        assert get_daily_usage(result["id"]) == 0

    def test_counts_todays_logs(self):
        result = create_api_key("test-app")
        conn = get_connection()
        try:
            cur = conn.cursor()
            for _ in range(5):
                cur.execute(
                    "INSERT INTO search_logs (query, result_count, api_key_id) VALUES (%s, %s, %s)",
                    ("test", 10, result["id"]),
                )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        assert get_daily_usage(result["id"]) == 5


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

    def test_search_with_valid_key_returns_usage(self):
        from fastapi.testclient import TestClient
        from frontend.api.main import app

        key_info = create_api_key("test-app")

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

    def test_search_with_key_via_query_param(self):
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
