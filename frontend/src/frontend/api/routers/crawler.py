import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from frontend.core.config import settings

router = APIRouter()


class CrawlRequest(BaseModel):
    url: str


@router.post("/crawl")
async def api_crawl(req: CrawlRequest):
    """Manually enqueue a URL via Crawler Service API."""
    url = req.url.strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls",
                json={"urls": [url], "priority": 1000.0},
            )

            if resp.status_code == 200:
                data = resp.json()
                added = data.get("added", 0) > 0
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
