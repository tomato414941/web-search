import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from frontend.api.middleware.rate_limiter import limiter
from frontend.core.config import settings

router = APIRouter()


class CrawlRequest(BaseModel):
    url: str


@router.post("/crawl")
@limiter.limit("10/minute")
async def api_crawl(request: Request, req: CrawlRequest):
    """Manually enqueue a URL via Crawler Service API."""
    url = req.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        headers: dict[str, str] = {}
        if settings.INDEXER_API_KEY:
            headers["X-API-Key"] = settings.INDEXER_API_KEY
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls",
                json={"urls": [url]},
                headers=headers,
            )

            if resp.status_code == 200:
                data = resp.json()
                added_count = data.get("added_count")
                if added_count is None:
                    # Backward compatibility for older crawler responses.
                    added_count = data.get("added", 0)
                added = added_count > 0
                msg = "Queued" if added else "Already seen (skipped)"
                return {"ok": True, "url": url, "message": msg, "added": added}
            else:
                return JSONResponse(
                    {"error": f"Crawler service error: {resp.text}"},
                    status_code=502,
                )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": f"Crawler service unavailable: {str(e)}"},
            status_code=503,
        )
