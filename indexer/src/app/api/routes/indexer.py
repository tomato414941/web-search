"""Indexer API Router - for remote crawler to submit pages."""

import logging
import secrets
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, HttpUrl, Field
from app.core.config import settings
from app.services.indexer import indexer_service
from app.services.index_jobs import IndexJobService
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
    outlinks: list[str] = Field(default_factory=list, max_length=500)


index_job_service = IndexJobService(
    settings.DB_PATH,
    max_retries=settings.INDEXER_JOB_MAX_RETRIES,
    retry_base_seconds=settings.INDEXER_JOB_RETRY_BASE_SEC,
    retry_max_seconds=settings.INDEXER_JOB_RETRY_MAX_SEC,
)


def verify_api_key(x_api_key: str) -> None:
    """Verify API key from header."""
    if not secrets.compare_digest(x_api_key, settings.INDEXER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/page", status_code=202)
async def submit_page(
    page: PageSubmission, x_api_key: str = Header(..., alias="X-API-Key")
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
            outlinks=page.outlinks,
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


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str, x_api_key: str = Header(..., alias="X-API-Key")
) -> dict:
    """Get asynchronous indexing job status."""
    verify_api_key(x_api_key)

    job = index_job_service.get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"ok": True, **job}


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
    queue_stats = index_job_service.get_queue_stats()

    return {
        "ok": True,
        "service": "indexer",
        "indexed_pages": stats.get("total", 0),
        **queue_stats,
    }
