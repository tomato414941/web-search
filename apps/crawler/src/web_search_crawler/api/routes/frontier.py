"""Frontier router."""

from fastapi import APIRouter, Depends
from web_search_crawler.api.deps import get_frontier_service
from web_search_crawler.models.frontier import FrontierItem
from web_search_crawler.services.frontier import FrontierService

router = APIRouter()


@router.get("/frontier", response_model=list[FrontierItem])
async def view_frontier(
    limit: int = 20, frontier_service: FrontierService = Depends(get_frontier_service)
):
    """Peek current frontier contents."""
    items = frontier_service.get_frontier_items(limit)
    return [FrontierItem(url=item["url"]) for item in items]
