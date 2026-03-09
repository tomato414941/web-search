"""Shared enums for statuses and modes across services.

Uses StrEnum so values work transparently as strings in SQL, JSON, and comparisons.
"""

from enum import StrEnum


class IndexJobStatus(StrEnum):
    """Indexer async job queue statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED_RETRY = "failed_retry"
    FAILED_PERMANENT = "failed_permanent"


CLAIMABLE_JOB_STATUSES = (IndexJobStatus.PENDING, IndexJobStatus.FAILED_RETRY)


class CrawlUrlStatus(StrEnum):
    """Crawler URL frontier lifecycle statuses."""

    PENDING = "pending"
    CRAWLING = "crawling"
    DONE = "done"
    FAILED = "failed"


class CrawlAttemptStatus(StrEnum):
    """Crawl attempt outcome statuses logged in crawl_logs."""

    QUEUED_FOR_INDEX = "queued_for_index"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    INDEXER_ERROR = "indexer_error"
    HTTP_ERROR = "http_error"
    UNKNOWN_ERROR = "unknown_error"
    DEAD_LETTER = "dead_letter"
    RETRY_LATER = "retry_later"


CRAWL_ERROR_STATUSES = (
    CrawlAttemptStatus.INDEXER_ERROR,
    CrawlAttemptStatus.HTTP_ERROR,
    CrawlAttemptStatus.UNKNOWN_ERROR,
    CrawlAttemptStatus.DEAD_LETTER,
)


class SearchMode(StrEnum):
    """Search mode for query execution."""

    BM25 = "bm25"
