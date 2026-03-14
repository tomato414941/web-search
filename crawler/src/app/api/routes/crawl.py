"""
Crawl Router

Handles crawl request endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.models.crawl import (
    CrawlNowRequest,
    CrawlNowResponse,
    CrawlRequest,
    CrawlResponse,
)
from app.services.queue import QueueService
from app.services.direct_crawl import crawl_url_now as execute_crawl_now
from app.api.deps import get_queue_service

router = APIRouter()


@router.post("/urls", response_model=CrawlResponse)
async def add_urls_to_queue(
    request: CrawlRequest,
    queue_service: QueueService = Depends(get_queue_service),
):
    """
    Add URLs to crawl queue

    URLs are added to crawl queue for asynchronous processing.
    Worker must be started separately via POST /worker/start.
    """
    try:
        count = await queue_service.enqueue_urls(
            urls=[str(url) for url in request.urls],
        )
        return CrawlResponse(status="queued", added_count=count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue URLs: {str(e)}")


@router.post("/crawl-now", response_model=CrawlNowResponse)
async def crawl_now(request: CrawlNowRequest):
    """Immediately crawl a single URL and queue it for indexing."""
    try:
        result = await execute_crawl_now(str(request.url))
        return CrawlNowResponse(
            status=result.status,
            url=result.url,
            message=result.message,
            job_id=result.job_id,
            outlinks_discovered=result.outlinks_discovered,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to crawl URL now: {str(e)}"
        )
