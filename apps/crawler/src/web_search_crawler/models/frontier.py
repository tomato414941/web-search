"""Pydantic models for frontier endpoints."""

from pydantic import BaseModel, Field


class FrontierItem(BaseModel):
    """Single item in the frontier."""

    url: str = Field(..., description="URL to be crawled")


class FrontierStats(BaseModel):
    """Overall frontier statistics."""

    pending: int = Field(
        default=0,
        ge=0,
        description="Number of pending frontier entries",
    )
    total_seen: int = Field(default=0, ge=0, description="Total unique URLs in history")


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="ok")
