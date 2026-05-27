"""Indexer API Router - for remote crawler to submit pages."""

import asyncio
import logging
import secrets
import time
from fastapi import APIRouter, HTTPException, Header
from web_search_indexer.core.config import settings
from web_search_indexer.metrics import update_indexed_pages_metric
from web_search_indexer.services.indexer import indexer_service
from web_search_indexer.services.index_job_container import index_job_service
from web_search_contracts.admin_read_models import (
    IndexerIndexSummaryApiResponse,
    IndexerJobFailureSummaryApiResponse,
)
from web_search_contracts.indexer_api import IndexPageRequest
from web_search_core.background import maintain_refresh_loop
from web_search_indexer.services.information_origin import calculate_information_origin
from web_search_indexer.services.pagerank import (
    calculate_domain_pagerank,
    calculate_pagerank,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indexer")

_index_summary_cache: dict[str, object] = {"data": None, "expires": 0.0}
_job_failure_summary_cache: dict[str, object] = {"data": None, "expires": 0.0}


def _clear_index_summary_cache() -> None:
    _index_summary_cache["data"] = None
    _index_summary_cache["expires"] = 0.0


def _clear_job_failure_summary_cache() -> None:
    _job_failure_summary_cache["data"] = None
    _job_failure_summary_cache["expires"] = 0.0


def _cache_index_summary_payload(payload: dict) -> dict:
    normalized = IndexerIndexSummaryApiResponse.model_validate(payload).model_dump(
        mode="json"
    )
    _index_summary_cache["data"] = normalized
    _index_summary_cache["expires"] = time.monotonic() + max(
        1, settings.INDEXER_STATS_CACHE_TTL_SEC
    )
    return normalized


def _cache_job_failure_summary_payload(payload: dict) -> dict:
    normalized = IndexerJobFailureSummaryApiResponse.model_validate(payload).model_dump(
        mode="json"
    )
    _job_failure_summary_cache["data"] = normalized
    _job_failure_summary_cache["expires"] = time.monotonic() + max(
        1, settings.INDEXER_STATS_CACHE_TTL_SEC
    )
    return normalized


async def _refresh_index_summary_cache() -> dict:
    stats = await asyncio.to_thread(indexer_service.get_index_stats)
    payload = {
        "ok": True,
        "service": "indexer",
        "indexed_pages": stats.get("total", 0),
    }
    update_indexed_pages_metric(payload["indexed_pages"])
    return _cache_index_summary_payload(payload)


async def _refresh_job_failure_summary_cache() -> dict:
    failure_stats = await asyncio.to_thread(index_job_service.get_failure_stats)
    payload = {
        "ok": True,
        "service": "indexer",
        **failure_stats,
    }
    return _cache_job_failure_summary_payload(payload)


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
        page_count = calculate_pagerank()
        domain_count = calculate_domain_pagerank()
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
        count = calculate_information_origin()
        return {"ok": True, "pages_scored": count}
    except Exception as e:
        logger.error("Origin score calculation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Origin score calculation failed")


@router.get("/index-summary", response_model=IndexerIndexSummaryApiResponse)
async def index_summary(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Indexer index summary."""
    verify_api_key(x_api_key)

    now = time.monotonic()
    cached = _index_summary_cache["data"]
    if cached is not None and now < float(_index_summary_cache["expires"]):
        update_indexed_pages_metric(cached["indexed_pages"])  # type: ignore[index]
        return cached  # type: ignore[return-value]

    return await _refresh_index_summary_cache()


@router.get(
    "/job-failure-summary",
    response_model=IndexerJobFailureSummaryApiResponse,
)
async def job_failure_summary(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Indexer job failure summary."""
    verify_api_key(x_api_key)

    now = time.monotonic()
    cached = _job_failure_summary_cache["data"]
    if cached is not None and now < float(_job_failure_summary_cache["expires"]):
        return cached  # type: ignore[return-value]

    return await _refresh_job_failure_summary_cache()


async def prewarm_summary_cache(
    *, attempts: int = 60, delay_seconds: float = 5.0
) -> None:
    for _attempt in range(attempts):
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        try:
            await asyncio.gather(
                _refresh_index_summary_cache(),
                _refresh_job_failure_summary_cache(),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to prewarm indexer summary cache: %s", exc)
            _clear_index_summary_cache()
            _clear_job_failure_summary_cache()
            continue
        logger.info("Prewarmed indexer summary cache")
        return

    logger.warning("Indexer summary prewarm gave up after %d attempts", attempts)


async def maintain_summary_cache(*, refresh_interval_seconds: float) -> None:
    async def refresh_once() -> None:
        await prewarm_summary_cache(attempts=1, delay_seconds=0)

    await maintain_refresh_loop(
        initial_call=prewarm_summary_cache,
        periodic_call=refresh_once,
        refresh_interval_seconds=refresh_interval_seconds,
    )
