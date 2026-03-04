"""Job recovery and maintenance operations."""

import logging
from typing import Any

from shared.contracts.enums import IndexJobStatus
from shared.core.retry import RetryPolicy
from shared.postgres.search import get_connection, sql_placeholder

logger = logging.getLogger(__name__)

STATUS_PENDING = IndexJobStatus.PENDING
STATUS_DONE = IndexJobStatus.DONE
STATUS_FAILED_RETRY = IndexJobStatus.FAILED_RETRY
STATUS_FAILED_PERMANENT = IndexJobStatus.FAILED_PERMANENT
STATUS_PROCESSING = IndexJobStatus.PROCESSING


def recover_expired_locked(cur: Any, now_ts: int, policy: RetryPolicy) -> None:
    """Reset expired leases: exhausted -> failed_permanent, others -> retry."""
    ph = sql_placeholder()
    cur.execute(
        f"""
        SELECT job_id, retry_count
        FROM index_jobs
        WHERE status = {ph}
          AND lease_until IS NOT NULL
          AND lease_until < {ph}
        """,
        (STATUS_PROCESSING, now_ts),
    )
    expired = cur.fetchall()
    if not expired:
        return

    exhausted_ids = []
    retryable_ids = []
    for job_id, retry_count in expired:
        next_retry = int(retry_count) + 1
        if policy.is_exhausted(next_retry):
            exhausted_ids.append(str(job_id))
        else:
            retryable_ids.append(str(job_id))

    if exhausted_ids:
        cur.execute(
            f"""
            UPDATE index_jobs
            SET
                status = {ph},
                retry_count = retry_count + 1,
                lease_until = NULL,
                worker_id = NULL,
                last_error = {ph},
                updated_at = {ph}
            WHERE job_id = ANY({ph})
            """,
            (STATUS_FAILED_PERMANENT, "Lease expired", now_ts, exhausted_ids),
        )

    if retryable_ids:
        base = policy.base_seconds
        cap = policy.max_seconds
        cur.execute(
            f"""
            UPDATE index_jobs
            SET
                status = {ph},
                retry_count = retry_count + 1,
                available_at = {ph} + LEAST(
                    {ph} * POWER(2, retry_count)::int, {ph}
                ),
                lease_until = NULL,
                worker_id = NULL,
                last_error = {ph},
                updated_at = {ph}
            WHERE job_id = ANY({ph})
            """,
            (
                STATUS_FAILED_RETRY,
                now_ts,
                base,
                cap,
                "Lease expired",
                now_ts,
                retryable_ids,
            ),
        )


def cleanup_old_done_jobs(
    db_path: str, now_ts: int, max_age_seconds: int = 7 * 86400
) -> int:
    """Delete completed jobs older than max_age_seconds. Returns deleted count."""
    cutoff = now_ts - max_age_seconds
    ph = sql_placeholder()
    con = get_connection(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            f"DELETE FROM index_jobs WHERE status = {ph} AND updated_at < {ph}",
            (STATUS_DONE, cutoff),
        )
        deleted = cur.rowcount
        con.commit()
        cur.close()
        if deleted > 0:
            logger.info("Cleaned up %d old done jobs", deleted)
        return deleted
    finally:
        con.close()


def get_failed_permanent_jobs(
    db_path: str, *, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Return failed_permanent jobs for admin visibility."""
    ph = sql_placeholder()
    con = get_connection(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            SELECT job_id, url, last_error, retry_count, created_at, updated_at
            FROM index_jobs
            WHERE status = {ph}
            ORDER BY updated_at DESC
            LIMIT {ph} OFFSET {ph}
            """,
            (STATUS_FAILED_PERMANENT, limit, offset),
        )
        rows = cur.fetchall()
        cur.close()
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
    finally:
        con.close()


def retry_failed_job(db_path: str, job_id: str, now_ts: int) -> bool:
    """Reset a failed_permanent job back to pending. Returns True if reset."""
    ph = sql_placeholder()
    con = get_connection(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            f"""
            UPDATE index_jobs
            SET status = {ph},
                retry_count = 0,
                available_at = {ph},
                lease_until = NULL,
                worker_id = NULL,
                last_error = NULL,
                updated_at = {ph}
            WHERE job_id = {ph} AND status = {ph}
            """,
            (STATUS_PENDING, now_ts, now_ts, job_id, STATUS_FAILED_PERMANENT),
        )
        affected = cur.rowcount
        con.commit()
        cur.close()
        return affected > 0
    finally:
        con.close()
