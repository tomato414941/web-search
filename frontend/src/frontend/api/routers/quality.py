from fastapi import APIRouter, HTTPException, Request

from frontend.api.middleware.rate_limiter import limiter
from frontend.services.analytics import get_quality_summary

router = APIRouter()

WINDOWS = {
    "24h": 24,
    "7d": 24 * 7,
}


@router.get("/quality/summary")
@limiter.limit("60/minute")
async def quality_summary(request: Request, window: str = "24h"):
    del request
    hours = WINDOWS.get(window)
    if hours is None:
        raise HTTPException(status_code=400, detail="window must be one of: 24h, 7d")
    return get_quality_summary(hours)
