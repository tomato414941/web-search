from fastapi import APIRouter
from shared.db.redis import get_redis
from frontend.core.config import settings
from frontend.services.search import search_service

router = APIRouter()


@router.get("/api/stats")
async def api_stats():
    """Return System Stats (Queue, Index, etc.)"""
    # Redis stats (Frontend's own implementation)
    r = get_redis()
    redis_stats = {
        "queued": r.zcard(settings.CRAWL_QUEUE_KEY),
        "visited": r.scard(settings.CRAWL_SEEN_KEY),
    }

    # DB stats (delegated to search service)
    db_stats = search_service.get_index_stats()

    return {"queue": redis_stats, "index": db_stats}
