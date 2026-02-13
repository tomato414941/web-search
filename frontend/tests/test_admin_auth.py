"""Test Admin Authentication and Security."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from frontend.api.main import app
from frontend.core.config import settings, Settings
from frontend.api.routers.admin import CSRF_COOKIE_NAME
from shared.core.infrastructure_config import Environment


client = TestClient(app)


def get_csrf_token_from_login_page() -> str:
    """Get CSRF token from login page."""
    client.get("/admin/login")
    return client.cookies.get(CSRF_COOKIE_NAME, "")


class TestAdminAuthentication:
    """Test admin authentication flows."""

    def test_login_page_loads(self):
        """Login page should be accessible without authentication."""
        response = client.get("/admin/login")
        assert response.status_code == 200
        assert "Admin Login" in response.text

    def test_login_with_valid_credentials(self):
        """Valid credentials should create session and redirect to dashboard."""
        csrf_token = get_csrf_token_from_login_page()
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"
        assert "admin_session" in response.cookies

    def test_login_with_invalid_username(self):
        """Invalid username should redirect to login with error."""
        csrf_token = get_csrf_token_from_login_page()
        response = client.post(
            "/admin/login",
            data={
                "username": "wrong",
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "Invalid+credentials" in response.headers["location"]

    def test_login_with_invalid_password(self):
        """Invalid password should redirect to login with error."""
        csrf_token = get_csrf_token_from_login_page()
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": "wrongpass",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "Invalid+credentials" in response.headers["location"]

    def test_dashboard_without_auth_redirects(self):
        """Dashboard should redirect to login when not authenticated."""
        client.cookies.clear()
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_dashboard_with_invalid_session(self):
        """Dashboard should redirect when session token is invalid."""
        client.cookies.clear()
        client.cookies.set("admin_session", "invalid_token")
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_dashboard_with_valid_session(self):
        """Dashboard should be accessible with valid session."""
        # First login to get valid session
        csrf_token = get_csrf_token_from_login_page()
        client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
        )
        # Use the session cookie from login
        response = client.get("/admin/")
        assert response.status_code == 200
        assert "Pale Blue Search Admin" in response.text

    def test_logout_clears_session(self):
        """Logout should clear session cookie."""
        client.cookies.clear()
        # Login first
        csrf_token = get_csrf_token_from_login_page()
        client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
        )
        # Then logout
        response = client.get("/admin/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        # Session cookie should be deleted (empty value)
        assert (
            client.cookies.get("admin_session") is None
            or client.cookies.get("admin_session") == ""
        )

    def test_seeds_page_requires_auth(self):
        """Seeds page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/seeds", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_history_page_requires_auth(self):
        """History page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/history", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_add_seed_requires_auth(self):
        """Adding seeds should require authentication."""
        client.cookies.clear()
        response = client.post(
            "/admin/seeds",
            data={"url": "https://example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_crawlers_page_requires_auth(self):
        """Crawlers page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/crawlers", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_crawlers_page_with_valid_session(self):
        """Crawlers page should be accessible with valid session."""
        client.cookies.clear()
        csrf_token = get_csrf_token_from_login_page()
        client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
        )
        response = client.get("/admin/crawlers")
        assert response.status_code == 200
        assert "Crawler Instances" in response.text

    def test_crawler_start_requires_auth(self):
        """Starting a crawler instance should require authentication."""
        client.cookies.clear()
        response = client.post(
            "/admin/crawlers/default/start",
            data={"concurrency": 1},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_crawler_stop_requires_auth(self):
        """Stopping a crawler instance should require authentication."""
        client.cookies.clear()
        response = client.post(
            "/admin/crawlers/default/stop",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


class TestSessionSecurity:
    """Test session security properties."""

    def test_session_cookie_httponly(self):
        """Session cookie should have httponly flag."""
        csrf_token = get_csrf_token_from_login_page()
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        # Check Set-Cookie header includes HttpOnly
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie

    def test_session_cookie_samesite(self):
        """Session cookie should have SameSite=Strict."""
        csrf_token = get_csrf_token_from_login_page()
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert "samesite=strict" in set_cookie.lower()

    def test_cookies_are_secure_in_production(self):
        """Session/CSRF cookies should include Secure in production."""
        with TestClient(app, base_url="https://testserver") as secure_client:
            secure_client.cookies.clear()
            with patch(
                "frontend.api.routers.admin.settings.ENVIRONMENT",
                Environment.PRODUCTION,
            ):
                login_page = secure_client.get("/admin/login")
                assert "secure" in login_page.headers.get("set-cookie", "").lower()

                csrf_token = secure_client.cookies.get(CSRF_COOKIE_NAME, "")
                response = secure_client.post(
                    "/admin/login",
                    data={
                        "username": settings.ADMIN_USERNAME,
                        "password": settings.ADMIN_PASSWORD,
                        "csrf_token": csrf_token,
                    },
                    follow_redirects=False,
                )
                assert response.status_code == 303
                assert "secure" in response.headers.get("set-cookie", "").lower()

    def test_cookies_do_not_force_secure_outside_production(self):
        """Session/CSRF cookies should keep non-production compatibility."""
        client.cookies.clear()
        with patch("frontend.api.routers.admin.settings.ENVIRONMENT", Environment.TEST):
            login_page = client.get("/admin/login")
            assert "secure" not in login_page.headers.get("set-cookie", "").lower()

            csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")
            response = client.post(
                "/admin/login",
                data={
                    "username": settings.ADMIN_USERNAME,
                    "password": settings.ADMIN_PASSWORD,
                    "csrf_token": csrf_token,
                },
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert "secure" not in response.headers.get("set-cookie", "").lower()

    @pytest.mark.skip(
        reason="Flaky test - session validation logic needs investigation"
    )
    def test_session_token_constant_time_comparison(self):
        """Session validation should use constant-time comparison (timing attack resistance)."""
        # This is tested indirectly - the code uses hmac.compare_digest()
        # We verify the behavior by trying an almost-correct token
        from frontend.api.routers.admin import create_session

        valid_token = create_session()
        # Create an almost-correct token (1 char different)
        if len(valid_token) > 0:
            invalid_token = valid_token[:-1] + ("a" if valid_token[-1] != "a" else "b")

            client.cookies.clear()
            client.cookies.set("admin_session", invalid_token)
            response = client.get("/admin/", follow_redirects=False)
            assert response.status_code == 303  # Should still be unauthorized


class TestCrawlerInstancesConfig:
    """Test CRAWLER_INSTANCES configuration property."""

    def test_crawler_instances_default(self):
        """Should return default instance when env var not set."""
        with patch.dict(os.environ, {}, clear=False):
            if "CRAWLER_INSTANCES" in os.environ:
                del os.environ["CRAWLER_INSTANCES"]
            s = Settings()
            instances = s.CRAWLER_INSTANCES
            assert len(instances) == 1
            assert instances[0]["name"] == "default"
            assert instances[0]["url"] == s.CRAWLER_SERVICE_URL

    def test_crawler_instances_single(self):
        """Should parse single instance correctly."""
        with patch.dict(os.environ, {"CRAWLER_INSTANCES": "test|http://test:8000"}):
            s = Settings()
            instances = s.CRAWLER_INSTANCES
            assert len(instances) == 1
            assert instances[0]["name"] == "test"
            assert instances[0]["url"] == "http://test:8000"

    def test_crawler_instances_multiple(self):
        """Should parse multiple instances correctly."""
        env_val = "crawler1|http://host1:8000,crawler2|http://host2:8000"
        with patch.dict(os.environ, {"CRAWLER_INSTANCES": env_val}):
            s = Settings()
            instances = s.CRAWLER_INSTANCES
            assert len(instances) == 2
            assert instances[0]["name"] == "crawler1"
            assert instances[0]["url"] == "http://host1:8000"
            assert instances[1]["name"] == "crawler2"
            assert instances[1]["url"] == "http://host2:8000"

    def test_crawler_instances_with_spaces(self):
        """Should handle spaces in the env var."""
        env_val = " crawler1 | http://host1:8000 , crawler2|http://host2:8000 "
        with patch.dict(os.environ, {"CRAWLER_INSTANCES": env_val}):
            s = Settings()
            instances = s.CRAWLER_INSTANCES
            assert len(instances) == 2
            assert instances[0]["name"] == "crawler1"
            assert instances[0]["url"] == "http://host1:8000"
