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
    last_queued: datetime | None = Field(None, description="When last added to queue")


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


class SeedRequeueRequest(BaseModel):
    """Request to requeue seeds"""

    force: bool = Field(
        default=False,
        description="If true, bypass crawl:seen check",
    )


class TrancoImportRequest(BaseModel):
    """Request to import seeds from Tranco list"""

    count: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Number of top domains to import",
    )


class SeedResponse(BaseModel):
    """Response for seed operations"""

    status: str = Field(default="ok")
    count: int = Field(default=0, description="Number of seeds affected")
