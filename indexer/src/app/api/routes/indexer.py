"""Indexer API Router - for remote crawler to submit pages."""

import secrets
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, HttpUrl
from typing import Optional

from app.core.config import settings
from app.services.indexer import indexer_service

router = APIRouter(prefix="/indexer")


class PageSubmission(BaseModel):
    """Page data submitted by crawler."""

    url: HttpUrl
    title: str
    content: str
    raw_html: Optional[str] = None


def verify_api_key(x_api_key: str) -> None:
    """Verify API key from header."""
    if not secrets.compare_digest(x_api_key, settings.INDEXER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/page")
async def submit_page(
    page: PageSubmission, x_api_key: str = Header(..., alias="X-API-Key")
) -> dict:
    """
    Submit a crawled page for indexing.

    Requires X-API-Key header for authentication.
    """
    # Verify API key
    verify_api_key(x_api_key)

    # Index the page (async)
    try:
        await indexer_service.index_page(
            url=str(page.url),
            title=page.title,
            content=page.content,
        )
        return {
            "ok": True,
            "message": "Page indexed successfully",
            "url": str(page.url),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/health")
async def health_check(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Health check endpoint for crawler."""
    verify_api_key(x_api_key)

    # Get index stats
    stats = indexer_service.get_index_stats()

    return {"ok": True, "service": "indexer", "indexed_pages": stats.get("total", 0)}
