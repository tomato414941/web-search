"""Shared index job service instance for API and workers."""

from web_search_indexer.core.config import settings
from web_search_indexer.services.index_jobs import IndexJobService


index_job_service = IndexJobService(
    max_retries=settings.INDEXER_JOB_MAX_RETRIES,
    retry_base_seconds=settings.INDEXER_JOB_RETRY_BASE_SEC,
    retry_max_seconds=settings.INDEXER_JOB_RETRY_MAX_SEC,
)


def configure_index_job_service() -> None:
    index_job_service.max_retries = settings.INDEXER_JOB_MAX_RETRIES
    index_job_service.retry_base_seconds = settings.INDEXER_JOB_RETRY_BASE_SEC
    index_job_service.retry_max_seconds = settings.INDEXER_JOB_RETRY_MAX_SEC
