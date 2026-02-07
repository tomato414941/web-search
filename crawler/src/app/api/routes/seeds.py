"""
Seeds Router

Handles seed URL management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.models.seeds import (
    SeedItem,
    SeedAddRequest,
    SeedDeleteRequest,
    SeedRequeueRequest,
    SeedResponse,
    TrancoImportRequest,
)
from app.services.seeds import SeedService
from app.services.tranco import download_tranco
from app.api.deps import get_seed_service

router = APIRouter()


@router.get("/seeds", response_model=list[SeedItem])
async def list_seeds(seed_service: SeedService = Depends(get_seed_service)):
    """Get all registered seed URLs"""
    return seed_service.list_seeds()


@router.post("/seeds", response_model=SeedResponse)
async def add_seeds(
    request: SeedAddRequest,
    seed_service: SeedService = Depends(get_seed_service),
):
    """
    Add URLs as seeds.

    Seeds are persisted and automatically added to the crawl queue.
    """
    try:
        count = seed_service.add_seeds(
            urls=[str(url) for url in request.urls],
            priority=request.priority,
        )
        return SeedResponse(status="ok", count=count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add seeds: {str(e)}")


@router.delete("/seeds", response_model=SeedResponse)
async def delete_seeds(
    request: SeedDeleteRequest,
    seed_service: SeedService = Depends(get_seed_service),
):
    """Remove URLs from seed list"""
    try:
        count = seed_service.delete_seeds(urls=[str(url) for url in request.urls])
        return SeedResponse(status="ok", count=count)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete seeds: {str(e)}")


@router.post("/seeds/import-tranco", response_model=SeedResponse)
async def import_tranco(
    request: TrancoImportRequest = TrancoImportRequest(),
    seed_service: SeedService = Depends(get_seed_service),
):
    """Import top domains from the Tranco list as seeds."""
    try:
        urls = download_tranco(count=request.count)
        count = seed_service.add_seeds(urls=urls, priority=request.priority)
        return SeedResponse(status="ok", count=count)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to import Tranco list: {str(e)}"
        )


@router.post("/seeds/requeue", response_model=SeedResponse)
async def requeue_all_seeds(
    request: SeedRequeueRequest = SeedRequeueRequest(),
    seed_service: SeedService = Depends(get_seed_service),
):
    """
    Re-add all seeds to the crawl queue.

    Set force=true to bypass crawl:seen check and force re-crawling.
    """
    try:
        count = seed_service.requeue_all(force=request.force)
        return SeedResponse(status="ok", count=count)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to requeue seeds: {str(e)}"
        )


@router.post("/seeds/{url:path}/requeue", response_model=SeedResponse)
async def requeue_one_seed(
    url: str,
    force: bool = False,
    seed_service: SeedService = Depends(get_seed_service),
):
    """
    Re-add a specific seed to the crawl queue.

    Set force=true to bypass crawl:seen check.
    """
    try:
        success = seed_service.requeue_one(url, force=force)
        if not success:
            raise HTTPException(
                status_code=404, detail="Seed URL not found or already in queue"
            )
        return SeedResponse(status="ok", count=1)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to requeue seed: {str(e)}")
