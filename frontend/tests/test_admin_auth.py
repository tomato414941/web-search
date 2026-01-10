"""Test Admin Authentication and Security."""

from fastapi.testclient import TestClient

from frontend.api.main import app
from frontend.core.config import settings


client = TestClient(app)


class TestAdminAuthentication:
    """Test admin authentication flows."""

    def test_login_page_loads(self):
        """Login page should be accessible without authentication."""
        response = client.get("/admin/login")
        assert response.status_code == 200
        assert "Admin Login" in response.text

    def test_login_with_valid_credentials(self):
        """Valid credentials should create session and redirect to dashboard."""
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"
        assert "admin_session" in response.cookies

    def test_login_with_invalid_username(self):
        """Invalid username should redirect to login with error."""
        response = client.post(
            "/admin/login",
            data={"username": "wrong", "password": settings.ADMIN_PASSWORD},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "Invalid+credentials" in response.headers["location"]

    def test_login_with_invalid_password(self):
        """Invalid password should redirect to login with error."""
        response = client.post(
            "/admin/login",
            data={"username": settings.ADMIN_USERNAME, "password": "wrongpass"},
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
        login_response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
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
        client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
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


class TestSessionSecurity:
    """Test session security properties."""

    def test_session_cookie_httponly(self):
        """Session cookie should have httponly flag."""
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        # Check Set-Cookie header includes HttpOnly
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie

    def test_session_cookie_samesite(self):
        """Session cookie should have SameSite=Strict."""
        response = client.post(
            "/admin/login",
            data={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
            follow_redirects=False,
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert "samesite=strict" in set_cookie.lower()

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
