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
    total_seen: int = Field(default=0, ge=0, description="Total unique URLs ever seen")
    active_seen: int = Field(
        default=0, ge=0, description="URLs seen within recrawl threshold"
    )
    cache_size: int = Field(
        default=0, ge=0, description="Redis cache size for fast lookups"
    )
    total_indexed: int = Field(
        default=0,
        ge=0,
        description="Total URLs successfully indexed",
    )
    # Backward compatible alias
    total_crawled: int = Field(
        default=0, ge=0, description="Alias for active_seen (backward compat)"
    )


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="ok")
