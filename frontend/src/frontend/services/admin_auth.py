import secrets
from datetime import timedelta

from fastapi import Request
from fastapi.responses import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from frontend.core.config import settings
from shared.core.infrastructure_config import Environment

SESSION_MAX_AGE_SECONDS = int(timedelta(hours=24).total_seconds())
SESSION_COOKIE_NAME = "admin_session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY)


def create_session() -> str:
    data = {"user": settings.ADMIN_USERNAME}
    return _serializer.dumps(data)


def validate_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_csrf_token(request: Request) -> str:
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
    return token


def validate_csrf_token(request: Request, form_token: str | None) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token or not form_token:
        return False
    return secrets.compare_digest(cookie_token, form_token)


def _secure_cookie_enabled() -> bool:
    return settings.ENVIRONMENT == Environment.PRODUCTION


def set_admin_cookie(
    response: Response,
    key: str,
    value: str,
    *,
    httponly: bool,
) -> Response:
    response.set_cookie(
        key,
        value,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=httponly,
        secure=_secure_cookie_enabled(),
        samesite="strict",
    )
    return response


def add_csrf_cookie(response: Response, token: str) -> Response:
    return set_admin_cookie(response, CSRF_COOKIE_NAME, token, httponly=False)


def add_session_cookie(response: Response, token: str) -> Response:
    return set_admin_cookie(response, SESSION_COOKIE_NAME, token, httponly=True)
