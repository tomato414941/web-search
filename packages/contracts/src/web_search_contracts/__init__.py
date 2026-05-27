"""Shared contracts: enums and typed models for inter-service communication."""

from web_search_contracts.admin_read_models import (
    CrawlerInstanceReadModel,
    CrawlerInstanceStatusReadModel,
    CrawlerInstancesReadModel,
    IndexerFailedJobsApiResponse,
    IndexerFailedJobReadModel,
    IndexerHealthReadModel,
    IndexerStatsApiResponse,
)
from web_search_contracts.enums import (
    CrawlAttemptStatus,
    CrawlUrlStatus,
    IndexJobStatus,
    SearchMode,
)
from web_search_contracts.indexer_api import IndexPageRequest, IndexPageResponse

__all__ = [
    "CrawlerInstanceReadModel",
    "CrawlerInstanceStatusReadModel",
    "CrawlerInstancesReadModel",
    "CrawlAttemptStatus",
    "CrawlUrlStatus",
    "IndexJobStatus",
    "IndexPageRequest",
    "IndexPageResponse",
    "IndexerFailedJobsApiResponse",
    "IndexerFailedJobReadModel",
    "IndexerHealthReadModel",
    "IndexerStatsApiResponse",
    "SearchMode",
]
