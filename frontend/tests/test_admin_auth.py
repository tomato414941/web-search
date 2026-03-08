"""Test Admin Authentication and Security."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import Response
from fastapi.testclient import TestClient

from frontend.api.main import app
from frontend.core.config import settings, Settings
from frontend.services.admin_auth import CSRF_COOKIE_NAME, create_session
from shared.core.infrastructure_config import Environment


def get_csrf_token_from_login_page(client: TestClient) -> str:
    """Get CSRF token from login page."""
    client.get("/admin/login")
    return client.cookies.get(CSRF_COOKIE_NAME, "")


def login_as_admin(client: TestClient, *, follow_redirects: bool = True):
    csrf_token = get_csrf_token_from_login_page(client)
    return client.post(
        "/admin/login",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
            "csrf_token": csrf_token,
        },
        follow_redirects=follow_redirects,
    )


class TestAdminAuthentication:
    """Test admin authentication flows."""

    def test_login_page_loads(self, client):
        """Login page should be accessible without authentication."""
        response = client.get("/admin/login")
        assert response.status_code == 200
        assert "Admin Login" in response.text

    def test_login_with_valid_credentials(self, client):
        """Valid credentials should create session and redirect to dashboard."""
        response = login_as_admin(client, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"
        assert "admin_session" in response.cookies

    def test_login_with_invalid_username(self, client):
        """Invalid username should redirect to login with error."""
        csrf_token = get_csrf_token_from_login_page(client)
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

    def test_login_with_invalid_password(self, client):
        """Invalid password should redirect to login with error."""
        csrf_token = get_csrf_token_from_login_page(client)
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

    def test_dashboard_without_auth_redirects(self, client):
        """Dashboard should redirect to login when not authenticated."""
        client.cookies.clear()
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_dashboard_with_invalid_session(self, client):
        """Dashboard should redirect when session token is invalid."""
        client.cookies.clear()
        client.cookies.set("admin_session", "invalid_token")
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_dashboard_with_valid_session(self, client):
        """Dashboard should be accessible with valid session."""
        login_as_admin(client)
        # Use the session cookie from login
        response = client.get("/admin/")
        assert response.status_code == 200
        assert "Pale Blue Search Admin" in response.text

    def test_logout_clears_session(self, client):
        """Logout should clear session cookie."""
        client.cookies.clear()
        login_as_admin(client)
        # Then logout
        response = client.get("/admin/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        # Session cookie should be deleted (empty value)
        assert (
            client.cookies.get("admin_session") is None
            or client.cookies.get("admin_session") == ""
        )

    def test_seeds_page_requires_auth(self, client):
        """Seeds page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/seeds", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_history_page_requires_auth(self, client):
        """History page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/history", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_seeds_page_with_valid_session(self, client):
        """Seeds page should be accessible with valid session."""
        client.cookies.clear()
        login_as_admin(client)
        response = client.get("/admin/seeds")
        assert response.status_code == 200
        assert "Seed URLs" in response.text
        assert "Registered Seeds" in response.text

    def test_add_seed_requires_auth(self, client):
        """Adding seeds should require authentication."""
        client.cookies.clear()
        response = client.post(
            "/admin/seeds",
            data={"url": "https://example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_crawlers_page_requires_auth(self, client):
        """Crawlers page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/crawlers", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_indexer_page_requires_auth(self, client):
        """Indexer page should require authentication."""
        client.cookies.clear()
        response = client.get("/admin/indexer", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_crawlers_page_with_valid_session(self, client):
        """Crawlers page should be accessible with valid session."""
        client.cookies.clear()
        login_as_admin(client)
        response = client.get("/admin/crawlers")
        assert response.status_code == 200
        assert "Crawler Instances" in response.text
        assert "Concurrency" in response.text
        assert "Attempts/h" in response.text
        assert "Indexed/h" in response.text
        assert "Success" in response.text
        assert "Errors/h" in response.text

    def test_indexer_page_with_valid_session(self, client):
        """Indexer page should be accessible with valid session."""
        client.cookies.clear()
        login_as_admin(client)
        response = client.get("/admin/indexer")
        assert response.status_code == 200
        assert "Indexer Status" in response.text
        assert "Job Queue" in response.text

    def test_crawler_start_requires_auth(self, client):
        """Starting a crawler instance should require authentication."""
        client.cookies.clear()
        response = client.post(
            "/admin/crawlers/default/start",
            data={"concurrency": 1},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_crawler_stop_requires_auth(self, client):
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

    def test_session_cookie_httponly(self, client):
        """Session cookie should have httponly flag."""
        response = login_as_admin(client, follow_redirects=False)
        # Check Set-Cookie header includes HttpOnly
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie

    def test_session_cookie_samesite(self, client):
        """Session cookie should have SameSite=Strict."""
        response = login_as_admin(client, follow_redirects=False)
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

    def test_cookies_do_not_force_secure_outside_production(self, client):
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

    def test_tampered_session_token_is_rejected(self, client):
        """Tampered session token should be rejected."""
        valid_token = create_session()
        assert valid_token

        payload, timestamp, signature = valid_token.split(".")
        replacement = "A" if signature[0] != "A" else "B"
        invalid_token = ".".join([payload, timestamp, replacement + signature[1:]])

        client.cookies.set("admin_session", invalid_token)
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


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
            assert instances[1]["name"] == "crawler2"
            assert instances[1]["url"] == "http://host2:8000"


class TestSeedImportValidation:
    def test_import_tranco_with_invalid_count_redirects_with_error(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        response = client.post(
            "/admin/seeds/import-tranco",
            data={"count": "abc", "csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert (
            response.headers["location"]
            == "/admin/seeds?error=Count%20must%20be%20an%20integer%20between%201%20and%2010000"
        )

    def test_import_tranco_accepts_comma_separated_count(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with patch(
            "frontend.services.crawler_admin_client.httpx.AsyncClient"
        ) as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"count": 1234}
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            response = client.post(
                "/admin/seeds/import-tranco",
                data={"count": "1,234", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert (
            response.headers["location"]
            == "/admin/seeds?success=Imported%201234%20seeds%20from%20Tranco%20top%201234"
        )
        assert mock_instance.post.await_args.kwargs["json"] == {"count": 1234}


class TestAdminMutationRedirects:
    def test_add_seed_success_redirects_with_success_message(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with patch("frontend.api.routers.admin.crawler_add_seed", new=AsyncMock()):
            response = client.post(
                "/admin/seeds",
                data={"url": "https://example.com", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert (
            response.headers["location"]
            == "/admin/seeds?success=Added%20seed%20https%3A%2F%2Fexample.com"
        )

    def test_add_seed_validation_error_redirects_with_error_message(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with patch(
            "frontend.api.routers.admin.crawler_add_seed",
            new=AsyncMock(side_effect=ValueError("Duplicate seed")),
        ):
            response = client.post(
                "/admin/seeds",
                data={"url": "https://example.com", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/seeds?error=Duplicate%20seed"

    def test_delete_seed_success_redirects_with_success_message(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with patch("frontend.api.routers.admin.crawler_delete_seed", new=AsyncMock()):
            response = client.post(
                "/admin/seeds/delete",
                data={"url": "https://example.com", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/seeds?success=Seed%20deleted"

    def test_add_to_queue_success_redirects_with_success_message(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with patch("frontend.api.routers.admin.enqueue_url", new=AsyncMock()):
            response = client.post(
                "/admin/queue",
                data={"url": "https://example.com", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert (
            response.headers["location"]
            == "/admin/queue?success=Added%20https%3A%2F%2Fexample.com%20to%20queue"
        )


class TestAdminCrawlerRoutes:
    def test_crawlers_page_renders_instances_from_wrapper(self, client):
        client.cookies.clear()
        login_as_admin(client)

        instances = [{"name": "default"}]
        with (
            patch(
                "frontend.api.routers.admin_crawlers._get_all_crawler_instances",
                new=AsyncMock(return_value=instances),
            ) as mock_get_all,
            patch(
                "frontend.api.routers.admin_crawlers.templates.TemplateResponse",
                return_value=Response("ok"),
            ) as mock_template,
        ):
            response = client.get("/admin/crawlers")

        assert response.status_code == 200
        mock_get_all.assert_awaited_once()
        _, _, context = mock_template.call_args.args
        assert context["instances"] == instances

    def test_crawler_start_redirects_after_starting_worker(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with (
            patch(
                "frontend.api.routers.admin_crawlers.start_worker", new=AsyncMock()
            ) as mock_start,
            patch(
                "frontend.api.routers.admin_crawlers.clear_crawler_instances_cache"
            ) as mock_clear,
        ):
            response = client.post(
                "/admin/crawler/start",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"
        mock_start.assert_awaited_once()
        mock_clear.assert_called_once_with()

    def test_crawler_stop_redirects_after_stopping_worker(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with (
            patch(
                "frontend.api.routers.admin_crawlers.stop_worker", new=AsyncMock()
            ) as mock_stop,
            patch(
                "frontend.api.routers.admin_crawlers.clear_crawler_instances_cache"
            ) as mock_clear,
        ):
            response = client.post(
                "/admin/crawler/stop",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"
        mock_stop.assert_awaited_once()
        mock_clear.assert_called_once_with()

    def test_crawler_instance_start_ignores_unknown_name(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with (
            patch(
                "frontend.api.routers.admin_crawlers._find_crawler_url",
                return_value=None,
            ) as mock_find,
            patch(
                "frontend.api.routers.admin_crawlers.start_crawler_instance",
                new=AsyncMock(),
            ) as mock_start,
        ):
            response = client.post(
                "/admin/crawlers/missing/start",
                data={"concurrency": 3, "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/crawlers"
        mock_find.assert_called_once()
        mock_start.assert_not_awaited()

    def test_crawler_instance_start_redirects_after_starting_instance(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with (
            patch(
                "frontend.api.routers.admin_crawlers._find_crawler_url",
                return_value="http://crawler:8000",
            ) as mock_find,
            patch(
                "frontend.api.routers.admin_crawlers.start_crawler_instance",
                new=AsyncMock(),
            ) as mock_start,
            patch(
                "frontend.api.routers.admin_crawlers.clear_crawler_instances_cache"
            ) as mock_clear,
        ):
            response = client.post(
                "/admin/crawlers/default/start",
                data={"concurrency": 3, "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/crawlers"
        mock_find.assert_called_once_with("default", settings.CRAWLER_INSTANCES)
        mock_start.assert_awaited_once_with("http://crawler:8000", 3)
        mock_clear.assert_called_once_with()

    def test_crawler_instance_stop_redirects_after_stopping_instance(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with (
            patch(
                "frontend.api.routers.admin_crawlers._find_crawler_url",
                return_value="http://crawler:8000",
            ) as mock_find,
            patch(
                "frontend.api.routers.admin_crawlers.stop_crawler_instance",
                new=AsyncMock(),
            ) as mock_stop,
            patch(
                "frontend.api.routers.admin_crawlers.clear_crawler_instances_cache"
            ) as mock_clear,
        ):
            response = client.post(
                "/admin/crawlers/default/stop",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/crawlers"
        mock_find.assert_called_once_with("default", settings.CRAWLER_INSTANCES)
        mock_stop.assert_awaited_once_with("http://crawler:8000")
        mock_clear.assert_called_once_with()


class TestAdminIndexerRoutes:
    def test_indexer_page_renders_stats_and_failed_jobs(self, client):
        client.cookies.clear()
        login_as_admin(client)

        health = {"status": "ok"}
        failed_jobs = [{"job_id": "job-1"}]
        with (
            patch(
                "frontend.api.routers.admin_indexer.fetch_indexer_stats",
                new=AsyncMock(return_value=health),
            ) as mock_stats,
            patch(
                "frontend.api.routers.admin_indexer.fetch_failed_jobs",
                new=AsyncMock(return_value=failed_jobs),
            ) as mock_failed,
        ):
            response = client.get("/admin/indexer")

        assert response.status_code == 200
        assert "Indexer Status" in response.text
        mock_stats.assert_awaited_once_with()
        mock_failed.assert_awaited_once_with(limit=50)

    def test_retry_job_redirects_after_retrying_failed_job(self, client):
        client.cookies.clear()
        login_as_admin(client)
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME, "")

        with patch(
            "frontend.api.routers.admin_indexer.retry_failed_job", new=AsyncMock()
        ) as mock_retry:
            response = client.post(
                "/admin/indexer/retry-job",
                data={"job_id": "job-1", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/indexer"
        mock_retry.assert_awaited_once_with("job-1")
