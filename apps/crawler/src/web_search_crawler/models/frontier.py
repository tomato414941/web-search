"""Pydantic models for crawler utility endpoints."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="ok")
