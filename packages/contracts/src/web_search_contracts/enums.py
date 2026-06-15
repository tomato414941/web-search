"""Shared enums for statuses and modes across services.

Uses StrEnum so values work transparently as strings in SQL, JSON, and comparisons.
"""

from collections.abc import Mapping
from enum import StrEnum


class CrawlUrlStatus(StrEnum):
    """Crawler URL lifecycle statuses."""

    PENDING = "pending"
    CRAWLING = "crawling"
    DONE = "done"
    FAILED = "failed"


class CrawlAttemptStatus(StrEnum):
    """Crawl attempt outcome statuses logged in crawl_logs."""

    INDEXED = "indexed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    INDEXER_ERROR = "indexer_error"
    HTTP_ERROR = "http_error"
    UNKNOWN_ERROR = "unknown_error"
    DEAD_LETTER = "dead_letter"
    RETRY_LATER = "retry_later"


class CrawlAttemptSummaryStatus(StrEnum):
    """Operator-facing summary statuses derived from raw crawl attempt events."""

    SUBMITTED = "submitted"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    RETRYING = "retrying"
    FAILED = "failed"


CRAWL_ERROR_STATUSES = (
    CrawlAttemptStatus.INDEXER_ERROR,
    CrawlAttemptStatus.HTTP_ERROR,
    CrawlAttemptStatus.UNKNOWN_ERROR,
    CrawlAttemptStatus.DEAD_LETTER,
)

CRAWL_ATTEMPT_SUMMARY_ORDER = (
    CrawlAttemptSummaryStatus.SUBMITTED,
    CrawlAttemptSummaryStatus.BLOCKED,
    CrawlAttemptSummaryStatus.SKIPPED,
    CrawlAttemptSummaryStatus.RETRYING,
    CrawlAttemptSummaryStatus.FAILED,
)

_CRAWL_ATTEMPT_SUMMARY_MAP = {
    str(CrawlAttemptStatus.INDEXED): str(CrawlAttemptSummaryStatus.SUBMITTED),
    str(CrawlAttemptStatus.BLOCKED): str(CrawlAttemptSummaryStatus.BLOCKED),
    str(CrawlAttemptStatus.SKIPPED): str(CrawlAttemptSummaryStatus.SKIPPED),
    str(CrawlAttemptStatus.RETRY_LATER): str(CrawlAttemptSummaryStatus.RETRYING),
    str(CrawlAttemptStatus.INDEXER_ERROR): str(CrawlAttemptSummaryStatus.FAILED),
    str(CrawlAttemptStatus.HTTP_ERROR): str(CrawlAttemptSummaryStatus.FAILED),
    str(CrawlAttemptStatus.UNKNOWN_ERROR): str(CrawlAttemptSummaryStatus.FAILED),
    str(CrawlAttemptStatus.DEAD_LETTER): str(CrawlAttemptSummaryStatus.FAILED),
}


def summarize_crawl_attempt_status(status: str) -> str:
    """Map a raw crawl attempt event into an operator-facing summary status."""

    raw_status = str(status or "")
    return _CRAWL_ATTEMPT_SUMMARY_MAP.get(raw_status, raw_status)


def summarize_crawl_attempt_counts(
    counts: Mapping[str, int],
) -> dict[str, int]:
    """Merge raw crawl attempt counts into summary-status buckets."""

    summary_counts: dict[str, int] = {}
    for raw_status, count in counts.items():
        summary_status = summarize_crawl_attempt_status(raw_status)
        summary_counts[summary_status] = summary_counts.get(summary_status, 0) + int(
            count
        )
    return summary_counts


class SearchMode(StrEnum):
    """Search mode for query execution."""

    BM25 = "bm25"
