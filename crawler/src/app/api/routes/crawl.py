"""
Crawl Router

Handles crawl request endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.models.crawl import CrawlRequest, CrawlResponse
from app.services.queue import QueueService
from app.api.deps import get_queue_service

router = APIRouter()


@router.post("/urls", response_model=CrawlResponse)
async def add_urls_to_queue(
    request: CrawlRequest,
    queue_service: QueueService = Depends(get_queue_service),
):
    """
    Add URLs to crawl queue

    URLs are added to Redis queue for asynchronous processing.
    Worker must be started separately via POST /worker/start.
    """
    try:
        count = await queue_service.enqueue_urls(
            urls=[str(url) for url in request.urls], priority=request.priority
        )
        return CrawlResponse(status="queued", added_count=count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue URLs: {str(e)}")
