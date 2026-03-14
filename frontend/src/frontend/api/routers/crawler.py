import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from frontend.api.middleware.rate_limiter import limiter
from frontend.core.config import settings

router = APIRouter()


class CrawlRequest(BaseModel):
    url: str


def _normalized_url(url: str) -> str:
    return url.strip()


def _internal_headers() -> dict[str, str]:
    if not settings.INDEXER_API_KEY:
        return {}
    return {"X-API-Key": settings.INDEXER_API_KEY}


def _require_internal_api_key(request: Request) -> None:
    expected = settings.INDEXER_API_KEY
    provided = request.headers.get("X-API-Key")
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


async def _enqueue_url(url: str) -> dict | JSONResponse:
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/urls",
                json={"urls": [url]},
                headers=_internal_headers(),
            )

            if resp.status_code == 200:
                data = resp.json()
                added_count = data.get("added_count", 0)
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


async def _crawl_url_now(url: str) -> dict | JSONResponse:
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/api/v1/crawl-now",
                json={"url": url},
                headers=_internal_headers(),
            )
            if resp.status_code == 200:
                return {"ok": True, **resp.json()}
            return JSONResponse(
                {"error": f"Crawler service error: {resp.text}"},
                status_code=502,
            )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": f"Crawler service unavailable: {str(e)}"},
            status_code=503,
        )


@router.post("/enqueue")
@limiter.limit("10/minute")
async def api_enqueue(request: Request, req: CrawlRequest):
    """Enqueue a URL for asynchronous crawling."""
    return await _enqueue_url(_normalized_url(req.url))


@router.post("/crawl")
@limiter.limit("10/minute")
async def api_crawl(request: Request, req: CrawlRequest):
    """Deprecated alias for enqueueing a URL for asynchronous crawling."""
    result = await _enqueue_url(_normalized_url(req.url))
    if isinstance(result, JSONResponse):
        return result
    return {
        **result,
        "deprecated": True,
        "replacement": "/api/v1/enqueue",
    }


@router.post("/crawl-now")
@limiter.limit("2/minute")
async def api_crawl_now(request: Request, req: CrawlRequest):
    """Immediately crawl a URL and submit it to the indexer."""
    _require_internal_api_key(request)
    return await _crawl_url_now(_normalized_url(req.url))
