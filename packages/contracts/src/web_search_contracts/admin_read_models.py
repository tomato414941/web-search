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
