"""
Worker Control Models

Pydantic models for worker management endpoints.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal


class WorkerStopRequest(BaseModel):
    """Request to stop worker"""

    graceful: bool = Field(
        default=True,
        description="If True, wait for current tasks to complete before stopping",
    )


class WorkerStartRequest(BaseModel):
    """Worker start request with concurrency control"""

    concurrency: int = Field(
        default=1, ge=1, le=100, description="Number of concurrent crawl tasks"
    )


class WorkerStartResponse(BaseModel):
    """Response after starting worker"""

    status: str = Field(default="started")
    message: str = Field(default="Crawler worker started")


class WorkerStopResponse(BaseModel):
    """Response after stopping worker"""

    status: str = Field(default="stopped")
    message: str


class WorkerStatus(BaseModel):
    """Worker status information"""

    status: Literal["running", "stopped"] = Field(
        ..., description="Current worker status"
    )
    active_tasks: int = Field(
        default=0, ge=0, description="Number of currently running crawl tasks"
    )
    started_at: datetime | None = Field(
        default=None, description="Timestamp when worker was started (None if stopped)"
    )
    uptime_seconds: float | None = Field(
        default=None, ge=0, description="Worker uptime in seconds (None if stopped)"
    )
    concurrency: int | None = Field(
        default=None,
        ge=1,
        description="Configured worker concurrency (None if stopped)",
    )
