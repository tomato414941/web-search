"""
Health Check Router
"""

from fastapi import APIRouter
from app.models.queue import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="ok")
