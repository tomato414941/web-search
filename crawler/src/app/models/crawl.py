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


class CrawlResponse(BaseModel):
    """Response after adding URLs to queue"""

    status: str = Field(default="queued", description="Status of the request")
    added_count: int = Field(
        ..., ge=0, description="Number of URLs successfully added to queue"
    )


class CrawlNowRequest(BaseModel):
    """Request to immediately crawl a single URL."""

    url: HttpUrl = Field(..., description="URL to crawl immediately")


class CrawlNowResponse(BaseModel):
    """Response for an immediate crawl request."""

    status: str = Field(..., description="queued_for_index, skipped, or failed")
    url: HttpUrl = Field(..., description="URL that was processed")
    message: str = Field(..., description="Human-readable crawl result")
    job_id: str | None = Field(default=None, description="Indexer job id when queued")
    outlinks_discovered: int = Field(
        default=0,
        ge=0,
        description="Number of outlinks discovered during crawl",
    )
