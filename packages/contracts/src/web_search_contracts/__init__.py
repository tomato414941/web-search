"""Shared contracts: enums and typed models for inter-service communication."""

from web_search_contracts.admin_read_models import (
    CrawlerInstanceReadModel,
    CrawlerInstanceStatusReadModel,
    CrawlerInstancesReadModel,
    CrawlerStatsApiResponse,
    IndexerAdminReadModel,
    IndexerFailedJobsApiResponse,
    IndexerFailedJobReadModel,
    IndexerHealthReadModel,
    IndexerStatsApiResponse,
    RecentErrorEntryReadModel,
    StatusBreakdownApiResponse,
    StatusBreakdownEntryReadModel,
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
    "CrawlerStatsApiResponse",
    "CrawlAttemptStatus",
    "CrawlUrlStatus",
    "IndexJobStatus",
    "IndexPageRequest",
    "IndexPageResponse",
    "IndexerAdminReadModel",
    "IndexerFailedJobsApiResponse",
    "IndexerFailedJobReadModel",
    "IndexerHealthReadModel",
    "IndexerStatsApiResponse",
    "RecentErrorEntryReadModel",
    "SearchMode",
    "StatusBreakdownApiResponse",
    "StatusBreakdownEntryReadModel",
]
