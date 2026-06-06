"""
Crawl Router

Handles crawl request endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from web_search_crawler.models.crawl import (
    CrawlRequest,
    CrawlResponse,
)
from web_search_crawler.api.deps import get_frontier_service
from web_search_crawler.services.frontier import FrontierService

router = APIRouter()


@router.post("/urls", response_model=CrawlResponse)
async def admit_urls_to_frontier(
    request: CrawlRequest,
    frontier_service: FrontierService = Depends(get_frontier_service),
):
    """
    Admit URLs into the crawl frontier.

    URLs are admitted into the durable frontier for asynchronous processing.
    Worker must be started separately via POST /worker/start.
    """
    try:
        count = await frontier_service.admit_urls(
            urls=[str(url) for url in request.urls],
        )
        return CrawlResponse(status="admitted", added_count=count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to admit URLs: {str(e)}")
