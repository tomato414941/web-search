from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from shared.db.redis import get_redis, enqueue_if_new

router = APIRouter()


class CrawlRequest(BaseModel):
    url: str


@router.post("/api/crawl")
async def api_crawl(req: CrawlRequest):
    """Manually enqueue a URL"""
    url = req.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    r = get_redis()
    # Force high priority (score=1000.0)
    added = enqueue_if_new(r, url, score=1000.0)

    msg = "Queued" if added else "Already seen (skipped)"
    return {"ok": True, "url": url, "message": msg, "added": added}
