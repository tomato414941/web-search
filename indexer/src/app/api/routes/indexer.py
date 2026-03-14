"""Indexer API Router - for remote crawler to submit pages."""

import asyncio
import logging
import secrets
import time
from fastapi import APIRouter, HTTPException, Header
from app.core.config import settings
from app.metrics import update_indexed_pages_metric
from app.services.indexer import indexer_service
from app.services.index_jobs import IndexJobService
from shared.contracts.indexer_api import IndexPageRequest
from shared.core.background import maintain_refresh_loop
from shared.search_kernel.information_origin import calculate_information_origin
from shared.search_kernel.pagerank import calculate_pagerank, calculate_domain_pagerank

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indexer")


index_job_service = IndexJobService(
    settings.DB_PATH,
    max_retries=settings.INDEXER_JOB_MAX_RETRIES,
    retry_base_seconds=settings.INDEXER_JOB_RETRY_BASE_SEC,
    retry_max_seconds=settings.INDEXER_JOB_RETRY_MAX_SEC,
)

_stats_cache: dict[str, object] = {"data": None, "expires": 0.0}
_failed_jobs_cache: dict[tuple[int, int], dict[str, object]] = {}


def _clear_stats_cache() -> None:
    _stats_cache["data"] = None
    _stats_cache["expires"] = 0.0


def _clear_failed_jobs_cache() -> None:
    _failed_jobs_cache.clear()


def _cache_stats_payload(payload: dict) -> dict:
    _stats_cache["data"] = payload
    _stats_cache["expires"] = time.monotonic() + max(
        1, settings.INDEXER_STATS_CACHE_TTL_SEC
    )
    return payload


async def _refresh_stats_cache() -> dict:
    stats = await asyncio.to_thread(indexer_service.get_index_stats)

    payload = {
        "ok": True,
        "service": "indexer",
        "indexed_pages": stats.get("total", 0),
    }
    update_indexed_pages_metric(payload["indexed_pages"])
    return _cache_stats_payload(payload)


def _cache_failed_jobs_payload(limit: int, offset: int, jobs: list[dict]) -> dict:
    payload = {"ok": True, "jobs": jobs, "count": len(jobs)}
    _failed_jobs_cache[(limit, offset)] = {
        "data": payload,
        "expires": time.monotonic() + max(1, settings.INDEXER_STATS_CACHE_TTL_SEC),
    }
    return payload


async def _refresh_failed_jobs_cache(limit: int, offset: int) -> dict:
    jobs = await asyncio.to_thread(
        index_job_service.get_failed_permanent_jobs, limit=limit, offset=offset
    )
    return _cache_failed_jobs_payload(limit, offset, jobs)


def verify_api_key(x_api_key: str) -> None:
    """Verify API key from header."""
    if not secrets.compare_digest(x_api_key, settings.INDEXER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/page", status_code=202)
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
            outlinks=page.outlinks,
            published_at=page.published_at,
            updated_at=page.updated_at,
            author=page.author,
            organization=page.organization,
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


@router.get("/jobs/failed")
async def get_failed_jobs(
    x_api_key: str = Header(..., alias="X-API-Key"),
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List permanently failed indexing jobs."""
    verify_api_key(x_api_key)
    limit = min(limit, 500)
    cached = _failed_jobs_cache.get((limit, offset))
    now = time.monotonic()
    if cached is not None and now < float(cached["expires"]):
        return cached["data"]  # type: ignore[return-value]

    return await _refresh_failed_jobs_cache(limit, offset)


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


@router.post("/jobs/{job_id}/retry")
async def retry_failed_job(
    job_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> dict:
    """Reset a permanently failed job back to pending for re-processing."""
    verify_api_key(x_api_key)
    success = index_job_service.retry_failed_job(job_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Job not found or not in failed_permanent status",
        )
    _clear_failed_jobs_cache()
    return {"ok": True, "job_id": job_id, "message": "Job reset to pending"}


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


@router.post("/origin-scores")
async def trigger_origin_scores(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> dict:
    """Recalculate information origin scores from the link graph."""
    verify_api_key(x_api_key)
    try:
        count = calculate_information_origin(settings.DB_PATH)
        return {"ok": True, "pages_scored": count}
    except Exception as e:
        logger.error("Origin score calculation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Origin score calculation failed")


@router.get("/stats")
async def indexer_stats(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Indexer statistics: page count and job queue metrics."""
    verify_api_key(x_api_key)

    now = time.monotonic()
    cached = _stats_cache["data"]
    if cached is not None and now < float(_stats_cache["expires"]):
        update_indexed_pages_metric(cached["indexed_pages"])  # type: ignore[index]
        return cached  # type: ignore[return-value]

    return await _refresh_stats_cache()


async def prewarm_stats_cache(
    *, attempts: int = 60, delay_seconds: float = 5.0
) -> None:
    for _attempt in range(attempts):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        try:
            await asyncio.gather(
                _refresh_stats_cache(),
                _refresh_failed_jobs_cache(limit=50, offset=0),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to prewarm indexer stats cache: %s", exc)
            _clear_stats_cache()
            _clear_failed_jobs_cache()
            continue
        logger.info("Prewarmed indexer stats cache")
        return

    logger.warning("Indexer stats prewarm gave up after %d attempts", attempts)


async def maintain_stats_cache(*, refresh_interval_seconds: float) -> None:
    async def refresh_once() -> None:
        await prewarm_stats_cache(attempts=1, delay_seconds=0)

    await maintain_refresh_loop(
        initial_call=prewarm_stats_cache,
        periodic_call=refresh_once,
        refresh_interval_seconds=refresh_interval_seconds,
    )
