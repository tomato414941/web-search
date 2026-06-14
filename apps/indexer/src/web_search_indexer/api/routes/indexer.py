"""Indexer API Router - for remote crawler to submit pages."""

import logging
import secrets
from fastapi import APIRouter, HTTPException, Header
from web_search_indexer.core.config import settings
from web_search_indexer.services.index_job_container import index_job_service
from web_search_contracts.indexer_api import IndexPageRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_api_key(x_api_key: str) -> None:
    """Verify API key from header."""
    if not secrets.compare_digest(x_api_key, settings.INDEXER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/indexing-jobs", status_code=202)
async def submit_page(
    page: IndexPageRequest, x_api_key: str = Header(..., alias="X-API-Key")
) -> dict:
    """
    Queue a crawled page for asynchronous indexing.

    Requires X-API-Key header for authentication.
    """
    verify_api_key(x_api_key)

    try:
        job_id, created = index_job_service.enqueue(
            url=str(page.url),
            title=page.title,
            content=page.content,
            outlinks_count=page.outlinks_count,
            published_at=page.published_at,
            updated_at=page.updated_at,
        )
        return {
            "ok": True,
            "queued": True,
            "job_id": job_id,
            "deduplicated": not created,
            "message": "Page queued for indexing",
            "url": str(page.url),
        }
    except Exception as e:
        logger.error(f"Queueing failed for {page.url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Queueing failed")
