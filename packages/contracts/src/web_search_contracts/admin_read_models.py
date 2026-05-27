"""Typed admin read models shared across frontend and services."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CrawlerInstanceStatusReadModel(BaseModel):
    state: str = "unreachable"
    uptime: float | int | None = Field(default=None, ge=0)
    concurrency: int | None = Field(default=None, ge=0)


class CrawlerInstanceReadModel(CrawlerInstanceStatusReadModel):
    name: str = ""
    url: str = ""


class CrawlerInstancesReadModel(BaseModel):
    instances: list[CrawlerInstanceReadModel] = Field(default_factory=list)
    snapshot_generated_at: str | None = None
    snapshot_loaded_from: str = "empty"


class IndexerHealthReadModel(BaseModel):
    reachable: bool = False
    ok: bool = False
    http_status: int | None = Field(default=None, ge=100)
    error: str | None = None
    indexed_pages: int = Field(default=0, ge=0)
    pending_jobs: int = Field(default=0, ge=0)
    processing_jobs: int = Field(default=0, ge=0)
    failed_permanent_jobs: int = Field(default=0, ge=0)


class IndexerStatsApiResponse(IndexerHealthReadModel):
    service: str = "indexer"
