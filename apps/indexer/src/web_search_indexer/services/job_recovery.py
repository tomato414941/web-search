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
