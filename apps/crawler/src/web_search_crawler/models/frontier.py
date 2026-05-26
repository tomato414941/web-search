"""Pydantic models for frontier endpoints."""

from pydantic import BaseModel, Field


class FrontierItem(BaseModel):
    """Single item in the frontier."""

    url: str = Field(..., description="URL to be crawled")


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="ok")
