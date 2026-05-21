"""
Crawl Request/Response Models

Pydantic models for crawl-related API endpoints.
"""

from typing import Literal

from pydantic import BaseModel, HttpUrl, Field


class CrawlRequest(BaseModel):
    """Request to add URLs to the crawl frontier."""

    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="List of URLs to crawl",
        examples=[["https://example.com", "https://example.org"]],
    )


class CrawlResponse(BaseModel):
    """Response after adding URLs to the frontier."""

    status: str = Field(default="admitted", description="Status of the request")
    added_count: int = Field(
        ..., ge=0, description="Number of URLs successfully admitted to the frontier"
    )


class CrawlNowRequest(BaseModel):
    """Request to immediately crawl a single URL."""

    url: HttpUrl = Field(..., description="URL to crawl immediately")


class CrawlNowResponse(BaseModel):
    """Response for an immediate crawl request."""

    status: Literal["submitted", "skipped", "failed", "busy"] = Field(
        ...,
        description="Immediate crawl result status",
    )
    url: HttpUrl = Field(..., description="URL that was processed")
    message: str = Field(..., description="Human-readable crawl result")
    job_id: str | None = Field(
        default=None,
        description="Indexer job id when the page was submitted to the indexer",
    )
    outlinks_discovered: int = Field(
        default=0,
        ge=0,
        description="Number of outlinks discovered during crawl",
    )
