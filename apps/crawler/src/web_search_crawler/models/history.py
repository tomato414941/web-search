"""Pydantic models for crawl history endpoints."""

from pydantic import BaseModel, Field


class CrawlHistoryEntry(BaseModel):
    """Single crawl attempt log entry."""

    id: int = Field(..., ge=1)
    url: str
    status: str
    http_code: int | None = None
    error_message: str | None = None
    precheck_ms: int | None = Field(default=None, ge=0)
    robots_ms: int | None = Field(default=None, ge=0)
    ssrf_ms: int | None = Field(default=None, ge=0)
    crawl_delay_ms: int | None = Field(default=None, ge=0)
    fetch_ms: int | None = Field(default=None, ge=0)
    fetch_request_ms: int | None = Field(default=None, ge=0)
    fetch_body_read_ms: int | None = Field(default=None, ge=0)
    parse_ms: int | None = Field(default=None, ge=0)
    submit_ms: int | None = Field(default=None, ge=0)
    total_ms: int | None = Field(default=None, ge=0)
    created_at: int = Field(..., ge=0)


class CrawlHistoryAdminEntry(BaseModel):
    """Operator-facing crawl history entry for admin pages."""

    id: int = Field(..., ge=1)
    url: str
    raw_status: str
    status_label: str
    status_tone: str
    http_code: int | None = None
    error_message: str | None = None
    precheck_ms: int | None = Field(default=None, ge=0)
    robots_ms: int | None = Field(default=None, ge=0)
    ssrf_ms: int | None = Field(default=None, ge=0)
    crawl_delay_ms: int | None = Field(default=None, ge=0)
    fetch_ms: int | None = Field(default=None, ge=0)
    fetch_request_ms: int | None = Field(default=None, ge=0)
    fetch_body_read_ms: int | None = Field(default=None, ge=0)
    parse_ms: int | None = Field(default=None, ge=0)
    submit_ms: int | None = Field(default=None, ge=0)
    total_ms: int | None = Field(default=None, ge=0)
    created_at: int = Field(..., ge=0)
