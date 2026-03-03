"""Pydantic models for Crawler -> Indexer API communication."""

from pydantic import BaseModel, Field, HttpUrl


class IndexPageRequest(BaseModel):
    """Request payload for POST /api/v1/indexer/page."""

    url: HttpUrl
    title: str = Field(max_length=1000)
    content: str = Field(max_length=1_000_000)
    outlinks: list[str] = Field(default_factory=list, max_length=500)
    published_at: str | None = Field(default=None, max_length=50)
    updated_at: str | None = Field(default=None, max_length=50)
    author: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)


class IndexPageResponse(BaseModel):
    """Response from POST /api/v1/indexer/page (202 Accepted)."""

    ok: bool
    queued: bool
    job_id: str
    deduplicated: bool
    message: str
    url: str
