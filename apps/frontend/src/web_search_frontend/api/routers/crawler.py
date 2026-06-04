import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from web_search_frontend.api.middleware.rate_limiter import limiter
from web_search_frontend.core.config import settings

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


async def _admit_url_to_frontier(url: str) -> dict | JSONResponse:
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/urls",
                json={"urls": [url]},
                headers=_internal_headers(),
            )

            if resp.status_code == 200:
                data = resp.json()
                added_count = data.get("added_count", 0)
                added = added_count > 0
                msg = "Admitted" if added else "Already present (skipped)"
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
                f"{settings.CRAWLER_SERVICE_URL}/crawl-requests",
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


@router.post("/crawler/urls")
@limiter.limit("10/minute")
async def api_urls(request: Request, req: CrawlRequest):
    """Admit a URL into the frontier for asynchronous crawling."""
    return await _admit_url_to_frontier(_normalized_url(req.url))


@router.post("/crawler/crawl-requests")
@limiter.limit("2/minute")
async def api_crawl_now(request: Request, req: CrawlRequest):
    """Immediately crawl a URL and submit it to the indexer."""
    _require_internal_api_key(request)
    return await _crawl_url_now(_normalized_url(req.url))
