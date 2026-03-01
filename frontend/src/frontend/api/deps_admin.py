"""Admin authentication and CSRF dependencies for FastAPI."""

from fastapi import Request

from frontend.services.admin_auth import (
    SESSION_COOKIE_NAME,
    validate_csrf_token,
    validate_session,
)


class AdminRedirectException(Exception):
    """Raised to redirect unauthenticated users to the login page."""

    def __init__(self, url: str = "/admin/login"):
        self.url = url


def require_admin_session(request: Request) -> None:
    """FastAPI dependency that ensures the request has a valid admin session."""
    if not validate_session(request.cookies.get(SESSION_COOKIE_NAME)):
        raise AdminRedirectException("/admin/login")


def check_csrf_or_redirect(
    request: Request, csrf_token: str | None, redirect_url: str
) -> None:
    """Validate CSRF token; raise redirect on failure."""
    if not validate_csrf_token(request, csrf_token):
        raise AdminRedirectException(redirect_url)
