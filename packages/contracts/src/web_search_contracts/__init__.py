"""Shared contracts: enums and typed models for inter-service communication."""

from web_search_contracts.admin_read_models import (
    CrawlAttemptSummaryApiResponse,
    CrawlerInstanceReadModel,
    CrawlerInstanceStatusReadModel,
    CrawlerInstancesReadModel,
    IndexerAdminReadModel,
    IndexerFailedJobsApiResponse,
    IndexerFailedJobReadModel,
    IndexerHealthReadModel,
    IndexerStatsApiResponse,
    RecentErrorEntryReadModel,
    RecentCrawlErrorsApiResponse,
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
    "CrawlAttemptSummaryApiResponse",
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
    "RecentCrawlErrorsApiResponse",
    "SearchMode",
    "StatusBreakdownApiResponse",
    "StatusBreakdownEntryReadModel",
]
