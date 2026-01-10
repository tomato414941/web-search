"""
Worker Control API Router

Handles worker start/stop/status endpoints.
"""

from fastapi import APIRouter, HTTPException
from app.models.worker import (
    WorkerStatus,
    WorkerStopRequest,
    WorkerStartRequest,
    WorkerStartResponse,
    WorkerStopResponse,
)
from app.workers.manager import worker_manager
from app.core.config import settings

router = APIRouter()


@router.post("/start", response_model=WorkerStartResponse)
async def start_worker(request: WorkerStartRequest = WorkerStartRequest()):
    """Start the background crawler worker with specified concurrency"""
    if worker_manager.is_running:
        raise HTTPException(status_code=400, detail="Worker is already running")

    # Validate concurrency against MAX_CONCURRENCY
    if request.concurrency > settings.CRAWL_CONCURRENCY:
        raise HTTPException(
            status_code=400,
            detail=f"Concurrency {request.concurrency} exceeds maximum allowed {settings.CRAWL_CONCURRENCY}",
        )

    try:
        await worker_manager.start(concurrency=request.concurrency)
        return WorkerStartResponse(
            status="started",
            message=f"Crawler worker started with concurrency={request.concurrency}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start worker: {str(e)}")


@router.post("/stop", response_model=WorkerStopResponse)
async def stop_worker(request: WorkerStopRequest):
    """Stop the background crawler worker"""
    if not worker_manager.is_running:
        raise HTTPException(status_code=400, detail="Worker is not running")

    try:
        await worker_manager.stop(graceful=request.graceful)
        message = f"Worker stopped {'gracefully' if request.graceful else 'forcefully'}"
        return WorkerStopResponse(status="stopped", message=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop worker: {str(e)}")


@router.get("/status", response_model=WorkerStatus)
async def get_worker_status():
    """Get current worker status"""
    return await worker_manager.get_status()
