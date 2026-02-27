"""Shared contracts: enums and typed models for inter-service communication."""

from shared.contracts.enums import (
    CrawlAttemptStatus,
    CrawlUrlStatus,
    IndexJobStatus,
    SearchMode,
)
from shared.contracts.indexer_api import IndexPageRequest, IndexPageResponse

__all__ = [
    "CrawlAttemptStatus",
    "CrawlUrlStatus",
    "IndexJobStatus",
    "IndexPageRequest",
    "IndexPageResponse",
    "SearchMode",
]
