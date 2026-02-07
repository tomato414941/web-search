"""Indexer API Router - for remote crawler to submit pages."""

import logging
import secrets
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

from app.core.config import settings
from app.services.indexer import indexer_service
from shared.pagerank import calculate_pagerank, calculate_domain_pagerank

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indexer")

# Content limits
MAX_TITLE_LENGTH = 1000
MAX_CONTENT_LENGTH = 1_000_000  # 1MB text


class PageSubmission(BaseModel):
    """Page data submitted by crawler."""

    url: HttpUrl
    title: str = Field(max_length=MAX_TITLE_LENGTH)
    content: str = Field(max_length=MAX_CONTENT_LENGTH)
    raw_html: Optional[str] = None
    outlinks: list[str] = Field(default_factory=list, max_length=500)


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
            outlinks=page.outlinks,
        )
        return {
            "ok": True,
            "message": "Page indexed successfully",
            "url": str(page.url),
        }
    except Exception as e:
        # Log full error details internally
        logger.error(f"Indexing failed for {page.url}: {e}", exc_info=True)
        # Return generic error to client (no internal details)
        raise HTTPException(status_code=500, detail="Indexing failed")


@router.post("/pagerank")
async def trigger_pagerank(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Manually trigger PageRank recalculation (both page and domain)."""
    verify_api_key(x_api_key)
    try:
        page_count = calculate_pagerank(settings.DB_PATH)
        domain_count = calculate_domain_pagerank(settings.DB_PATH)
        return {
            "ok": True,
            "page_ranks": page_count,
            "domain_ranks": domain_count,
        }
    except Exception as e:
        logger.error(f"PageRank calculation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="PageRank calculation failed")


@router.get("/health")
async def health_check(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Health check endpoint for crawler."""
    verify_api_key(x_api_key)

    # Get index stats
    stats = indexer_service.get_index_stats()

    return {"ok": True, "service": "indexer", "indexed_pages": stats.get("total", 0)}
