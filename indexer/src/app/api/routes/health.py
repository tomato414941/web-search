"""Health check endpoint (public, no auth required)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Public health check endpoint for load balancer."""
    return {"status": "ok", "service": "indexer"}
