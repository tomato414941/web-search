"""FastAPI dependencies for API authentication."""

import asyncio

from fastapi import HTTPException, Request

from frontend.services.api_key import get_daily_usage, validate_api_key


async def optional_api_key(request: Request) -> dict | None:
    """Extract and validate API key from X-API-Key header or api_key query param.

    Returns None for anonymous requests (web UI).
    Raises 401 for invalid keys, 429 for rate limit exceeded.
    """
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not key:
        return None

    key_info = await asyncio.to_thread(validate_api_key, key)
    if key_info is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    usage = await asyncio.to_thread(get_daily_usage, key_info["id"])
    if usage >= key_info["rate_limit_daily"]:
        raise HTTPException(
            status_code=429,
            detail=f"Daily rate limit exceeded ({key_info['rate_limit_daily']}/day)",
        )

    key_info["daily_used"] = usage
    return key_info


async def require_api_key(request: Request) -> dict:
    """Require a valid API key. Raises 401 if missing or invalid."""
    result = await optional_api_key(request)
    if result is None:
        raise HTTPException(status_code=401, detail="API key required")
    return result
