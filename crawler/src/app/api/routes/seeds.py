"""
Seeds Router

Handles seed URL management endpoints.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.seeds import (
    SeedItem,
    SeedAddRequest,
    SeedDeleteRequest,
    SeedListResponse,
    SeedResponse,
    TrancoImportRequest,
)
from app.services.seeds import SeedService
from app.services.tranco import download_tranco
from app.api.deps import get_seed_service

router = APIRouter()
_seeds_cache: dict[tuple[int | None, int], dict[str, object]] = {}
_SEEDS_TTL = 120


def _clear_seeds_cache() -> None:
    _seeds_cache.clear()


@router.get("/seeds", response_model=list[SeedItem] | SeedListResponse)
async def list_seeds(
    seed_service: SeedService = Depends(get_seed_service),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
):
    """Get all registered seed URLs"""
    now = time.monotonic()
    cache_key = (
        (limit, offset) if include_total or limit is not None or offset else (None, 0)
    )
    cached = _seeds_cache.get(cache_key)
    if cached is not None and now < float(cached["expires"]):
        return cached["data"]  # type: ignore[return-value]

    if include_total or limit is not None or offset:
        payload = seed_service.list_seeds_page(limit=limit or 50, offset=offset)
    else:
        payload = seed_service.list_seeds()

    _seeds_cache[cache_key] = {"data": payload, "expires": now + _SEEDS_TTL}
    return payload


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
        )
        _clear_seeds_cache()
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
        _clear_seeds_cache()
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
        count = seed_service.add_seeds(urls=urls)
        _clear_seeds_cache()
        return SeedResponse(status="ok", count=count)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to import Tranco list: {str(e)}"
        )
