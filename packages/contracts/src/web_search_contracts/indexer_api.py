"""Pydantic models for Crawler -> Indexer API communication."""

from pydantic import BaseModel, Field, HttpUrl


class IndexDocumentRequest(BaseModel):
    """Request payload for POST /documents."""

    url: HttpUrl
    title: str = Field(max_length=1000)
    content: str = Field(max_length=1_000_000)


class IndexDocumentResponse(BaseModel):
    """Response from POST /documents."""

    ok: bool
    indexed: bool
    url: str
