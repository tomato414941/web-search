"""
Seed URL Models

Pydantic models for seed URL management endpoints.
"""

from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field


class SeedItem(BaseModel):
    """Single seed URL with metadata"""

    url: str = Field(..., description="Seed URL")
    added_at: datetime = Field(..., description="When the seed was added")
    priority: float = Field(default=100.0, description="Priority score")
    last_queued: datetime | None = Field(None, description="When last added to queue")


class SeedAddRequest(BaseModel):
    """Request to add seed URLs"""

    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="List of URLs to add as seeds",
    )
    priority: float = Field(
        default=100.0,
        ge=0.0,
        le=1000.0,
        description="Priority score (higher = crawled sooner)",
    )


class SeedDeleteRequest(BaseModel):
    """Request to delete seed URLs"""

    urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="List of URLs to remove from seeds",
    )


class SeedRequeueRequest(BaseModel):
    """Request to requeue seeds"""

    force: bool = Field(
        default=False,
        description="If true, bypass crawl:seen check",
    )


class SeedResponse(BaseModel):
    """Response for seed operations"""

    status: str = Field(default="ok")
    count: int = Field(default=0, description="Number of seeds affected")
