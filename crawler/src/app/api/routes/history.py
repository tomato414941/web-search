"""
History Router

Crawl history viewing endpoints.
"""

from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()


@router.get("/history")
async def get_crawl_history(
    url: Optional[str] = Query(None, description="Filter by specific URL"),
    limit: int = Query(
        50, ge=1, le=1000, description="Maximum number of records to return"
    ),
):
    """
    Get crawl history

    Returns recent crawl attempts with status, timestamps, and error information.
    """
    from app.utils.history import get_recent_history, get_url_history

    if url:
        # Get history for specific URL
        return get_url_history(url, limit=limit)
    else:
        # Get recent history
        return get_recent_history(limit=limit)
