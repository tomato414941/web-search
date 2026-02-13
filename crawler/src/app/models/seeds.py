"""
Seed URL Models

Pydantic models for seed URL management endpoints.
"""

from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field


class SeedItem(BaseModel):
    """Single seed URL with metadata"""

    url: str = Field(..., description="Seed URL")
    status: str = Field(..., description="URL status (pending/crawling/done/failed)")
    priority: float = Field(0, description="Crawl priority")
    created_at: datetime = Field(..., description="When the URL was first added")
    last_crawled_at: datetime | None = Field(None, description="When last crawled")


class SeedAddRequest(BaseModel):
    """Request to add seed URLs"""

    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="List of URLs to add as seeds",
    )


class SeedDeleteRequest(BaseModel):
    """Request to delete seed URLs"""

    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="List of URLs to remove from seeds",
    )


class TrancoImportRequest(BaseModel):
    """Request to import seeds from Tranco list"""

    count: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Number of top domains to import",
    )


class SeedResponse(BaseModel):
    """Response for seed operations"""

    status: str = Field(default="ok")
    count: int = Field(default=0, description="Number of seeds affected")
