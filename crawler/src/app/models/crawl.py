"""
Crawl Request/Response Models

Pydantic models for crawl-related API endpoints.
"""

from pydantic import BaseModel, HttpUrl, Field


class CrawlRequest(BaseModel):
    """Request to add URLs to crawl queue"""

    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="List of URLs to crawl",
        examples=[["https://example.com", "https://example.org"]],
    )
    priority: float = Field(
        default=100.0,
        ge=0.0,
        le=1000.0,
        description="Priority score (higher = crawled sooner)",
    )


class CrawlResponse(BaseModel):
    """Response after adding URLs to queue"""

    status: str = Field(default="queued", description="Status of the request")
    added_count: int = Field(
        ..., ge=0, description="Number of URLs successfully added to queue"
    )
