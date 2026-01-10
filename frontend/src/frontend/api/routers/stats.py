from fastapi import APIRouter
import httpx
from frontend.core.config import settings
from frontend.services.search import search_service

router = APIRouter()


@router.get("/stats")
async def api_stats():
    """Return System Stats (Queue, Index, etc.)"""
    # Crawler stats (via API)
    redis_stats = {"queued": 0, "visited": 0}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.CRAWLER_SERVICE_URL}/api/v1/status")
            if resp.status_code == 200:
                data = resp.json()
                redis_stats["queued"] = data.get("queued", 0)
                redis_stats["visited"] = data.get("visited", 0)
    except Exception:
        pass

    # DB stats (delegated to search service)
    db_stats = search_service.get_index_stats()

    return {"queue": redis_stats, "index": db_stats}
