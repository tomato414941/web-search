"""Typed admin read models shared across frontend and services."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CrawlerInstanceStatusReadModel(BaseModel):
    state: str = "unreachable"
    frontier_pending: int = Field(default=0, ge=0)
    uptime: float | int | None = Field(default=None, ge=0)
    concurrency: int | None = Field(default=None, ge=0)


class CrawlerInstanceReadModel(CrawlerInstanceStatusReadModel):
    name: str = ""
    url: str = ""


class CrawlerInstancesReadModel(BaseModel):
    instances: list[CrawlerInstanceReadModel] = Field(default_factory=list)
    snapshot_generated_at: str | None = None
    snapshot_loaded_from: str = "empty"


class RecentErrorEntryReadModel(BaseModel):
    url: str = Field(default="")
    error_message: str = Field(default="Unknown")
    created_at: int = Field(default=0, ge=0)


class RecentCrawlErrorsApiResponse(BaseModel):
    errors: list[RecentErrorEntryReadModel] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class StatusBreakdownEntryReadModel(BaseModel):
    status: str = ""
    count: int = Field(default=0, ge=0)
    pct: float = Field(default=0.0, ge=0.0)


class StatusBreakdownApiResponse(BaseModel):
    total: int = Field(default=0, ge=0)
    submitted: int = Field(default=0, ge=0)
    submit_rate_pct: float = Field(default=0.0, ge=0.0)
    hours: int | None = Field(default=None, ge=1)
    breakdown: list[StatusBreakdownEntryReadModel] = Field(default_factory=list)


class IndexerHealthReadModel(BaseModel):
    reachable: bool = False
    ok: bool = False
    http_status: int | None = Field(default=None, ge=100)
    error: str | None = None
    indexed_pages: int = Field(default=0, ge=0)
    pending_jobs: int = Field(default=0, ge=0)
    processing_jobs: int = Field(default=0, ge=0)
    failed_permanent_jobs: int = Field(default=0, ge=0)


class IndexerFailedJobReadModel(BaseModel):
    job_id: str = ""
    url: str | None = None
    last_error: str | None = None
    retry_count: int | None = Field(default=None, ge=0)
    created_at: int | str | None = None
    updated_at: int | str | None = None


class IndexerStatsApiResponse(IndexerHealthReadModel):
    service: str = "indexer"


class IndexerFailedJobsApiResponse(BaseModel):
    ok: bool = True
    jobs: list[IndexerFailedJobReadModel] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)


class IndexerAdminReadModel(BaseModel):
    health: IndexerHealthReadModel = Field(default_factory=IndexerHealthReadModel)
    failed_jobs: list[IndexerFailedJobReadModel] = Field(default_factory=list)
    snapshot_generated_at: str | None = None
    snapshot_loaded_from: str = "empty"
