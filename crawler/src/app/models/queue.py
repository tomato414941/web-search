"""
Queue Models

Pydantic models for queue-related endpoints.
"""

from pydantic import BaseModel, Field


class QueueItem(BaseModel):
    """Single item in the crawl queue"""

    url: str = Field(..., description="URL to be crawled")
    score: float = Field(..., description="Priority score (higher = crawled sooner)")


class QueueStats(BaseModel):
    """Overall queue statistics"""

    queue_size: int = Field(default=0, ge=0, description="Number of URLs in queue")
    total_crawled: int = Field(
        default=0, ge=0, description="Total number of URLs crawled (lifetime)"
    )
    total_indexed: int = Field(
        default=0,
        ge=0,
        description="Total number of URLs successfully indexed (lifetime)",
    )


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="ok")
