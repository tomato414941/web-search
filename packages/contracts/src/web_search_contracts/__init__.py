"""Shared contracts: enums and typed models for inter-service communication."""

from web_search_contracts.enums import (
    CrawlAttemptStatus,
    CrawlUrlStatus,
    SearchMode,
)
from web_search_contracts.indexer_api import (
    IndexDocumentRequest,
    IndexDocumentResponse,
)

__all__ = [
    "CrawlAttemptStatus",
    "CrawlUrlStatus",
    "IndexDocumentRequest",
    "IndexDocumentResponse",
    "SearchMode",
]
