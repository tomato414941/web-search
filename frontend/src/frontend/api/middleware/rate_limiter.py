# Rate Limiter Middleware for FastAPI
# Uses slowapi for IP-based rate limiting

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


# Disable rate limiting in test environment
_enabled = os.getenv("ENVIRONMENT", "").lower() != "test"
limiter = Limiter(key_func=get_remote_address, enabled=_enabled)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Too many requests. {exc.detail}",
        },
    )
