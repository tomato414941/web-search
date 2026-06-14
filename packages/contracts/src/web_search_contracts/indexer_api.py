"""Pydantic models for Crawler -> Indexer API communication."""

from pydantic import BaseModel, Field, HttpUrl


class IndexPageRequest(BaseModel):
    """Request payload for POST /indexing-jobs."""

    url: HttpUrl
    title: str = Field(max_length=1000)
    content: str = Field(max_length=1_000_000)


class IndexPageResponse(BaseModel):
    """Response from POST /indexing-jobs (202 Accepted)."""

    ok: bool
    queued: bool
    job_id: str
    deduplicated: bool
    message: str
    url: str
