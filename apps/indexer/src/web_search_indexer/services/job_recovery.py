"""Job recovery and maintenance operations."""

import logging
from typing import Any

from web_search_contracts.enums import IndexJobStatus
from web_search_core.retry import RetryPolicy
from web_search_postgres.repositories.index_job_repo import IndexJobRepository

logger = logging.getLogger(__name__)

STATUS_PENDING = IndexJobStatus.PENDING
STATUS_DONE = IndexJobStatus.DONE
STATUS_FAILED_RETRY = IndexJobStatus.FAILED_RETRY
STATUS_FAILED_PERMANENT = IndexJobStatus.FAILED_PERMANENT
STATUS_PROCESSING = IndexJobStatus.PROCESSING


def recover_expired_locked(cur: Any, now_ts: int, policy: RetryPolicy) -> None:
    """Reset expired leases: exhausted -> failed_permanent, others -> retry."""
    IndexJobRepository.recover_expired_locked(
        cur,
        now_ts=now_ts,
        policy=policy,
        status_processing=STATUS_PROCESSING,
        status_failed_retry=STATUS_FAILED_RETRY,
        status_failed_permanent=STATUS_FAILED_PERMANENT,
    )


def cleanup_old_done_jobs(now_ts: int, max_age_seconds: int = 7 * 86400) -> int:
    """Delete completed jobs older than max_age_seconds. Returns deleted count."""
    cutoff = now_ts - max_age_seconds
    deleted = IndexJobRepository.cleanup_old_done_jobs(
        now_ts=now_ts,
        cutoff=cutoff,
        status_done=STATUS_DONE,
    )
    if deleted > 0:
        logger.info("Cleaned up %d old done jobs", deleted)
    return deleted


def get_failed_permanent_jobs(
    *, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Return failed_permanent jobs for admin visibility."""
    rows = IndexJobRepository.list_failed_permanent_jobs(
        status_failed_permanent=STATUS_FAILED_PERMANENT,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "job_id": str(row[0]),
            "url": str(row[1]),
            "last_error": row[2],
            "retry_count": int(row[3]),
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]


def retry_failed_job(job_id: str, now_ts: int) -> bool:
    """Reset a failed_permanent job back to pending. Returns True if reset."""
    return IndexJobRepository.retry_failed_job(
        job_id=job_id,
        now_ts=now_ts,
        status_pending=STATUS_PENDING,
        status_failed_permanent=STATUS_FAILED_PERMANENT,
    )
