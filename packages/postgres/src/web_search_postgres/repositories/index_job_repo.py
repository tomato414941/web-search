"""Repository for index_jobs table operations."""

from typing import Any

from web_search_core.retry import RetryPolicy
from web_search_postgres.search import get_connection, sql_placeholder

ACTIVE_INDEX_JOB_STATUSES = ("pending", "processing", "failed_retry")


def _active_status_sql() -> str:
    return ", ".join(f"'{status}'" for status in ACTIVE_INDEX_JOB_STATUSES)


class IndexJobRepository:
    """Data-access layer for index_jobs operations."""

    @staticmethod
    def enqueue(
        *,
        job_id: str,
        url: str,
        title: str,
        content: str,
        status_pending: str,
        now_ts: int,
    ) -> tuple[str, bool]:
        ph = sql_placeholder()
        active_statuses = _active_status_sql()
        con = get_connection()
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                INSERT INTO index_jobs (
                    job_id, url, title, content,
                    status, retry_count,
                    available_at, lease_until, worker_id, last_error,
                    created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph},
                    {ph}, 0,
                    {ph}, NULL, NULL, NULL,
                    {ph}, {ph}
                )
                ON CONFLICT (url)
                WHERE status IN ({active_statuses})
                DO NOTHING
                RETURNING job_id
                """,
                (
                    job_id,
                    url,
                    title,
                    content,
                    status_pending,
                    now_ts,
                    now_ts,
                    now_ts,
                ),
            )
            row = cur.fetchone()
            if row:
                con.commit()
                cur.close()
                return str(row[0]), True

            cur.execute(
                f"""
                SELECT job_id
                FROM index_jobs
                WHERE url = {ph}
                  AND status IN ({active_statuses})
                ORDER BY created_at ASC, job_id ASC
                LIMIT 1
                """,
                (url,),
            )
            existing = cur.fetchone()
            con.commit()
            cur.close()
            if not existing:
                raise RuntimeError("Failed to resolve active index job")
            return str(existing[0]), False
        finally:
            con.close()

    @staticmethod
    def claim_jobs(
        *,
        now_ts: int,
        lease_until: int,
        limit: int,
        worker_id: str,
        status_pending: str,
        status_failed_retry: str,
        status_failed_permanent: str,
        status_processing: str,
        policy: RetryPolicy,
    ) -> list[tuple[Any, ...]]:
        ph = sql_placeholder()
        con = get_connection()
        try:
            cur = con.cursor()
            IndexJobRepository.recover_expired_locked(
                cur,
                now_ts=now_ts,
                policy=policy,
                status_processing=status_processing,
                status_failed_retry=status_failed_retry,
                status_failed_permanent=status_failed_permanent,
            )
            cur.execute(
                f"""
                WITH candidates AS (
                    SELECT job_id
                    FROM index_jobs
                    WHERE status IN ({ph}, {ph}) AND available_at <= {ph}
                    ORDER BY available_at ASC, created_at ASC
                    LIMIT {ph}
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE index_jobs AS j
                SET
                    status = {ph},
                    lease_until = {ph},
                    worker_id = {ph},
                    updated_at = {ph}
                FROM candidates c
                WHERE j.job_id = c.job_id
                RETURNING
                    j.job_id, j.url, j.title, j.content,
                    j.status, j.retry_count
                """,
                (
                    status_pending,
                    status_failed_retry,
                    now_ts,
                    limit,
                    status_processing,
                    lease_until,
                    worker_id,
                    now_ts,
                ),
            )
            rows = cur.fetchall()
            con.commit()
            cur.close()
            return rows
        finally:
            con.close()

    @staticmethod
    def recover_expired_locked(
        cur: Any,
        *,
        now_ts: int,
        policy: RetryPolicy,
        status_processing: str,
        status_failed_retry: str,
        status_failed_permanent: str,
    ) -> None:
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT job_id, retry_count
            FROM index_jobs
            WHERE status = {ph}
              AND lease_until IS NOT NULL
              AND lease_until < {ph}
            """,
            (status_processing, now_ts),
        )
        expired = cur.fetchall()
        if not expired:
            return

        exhausted_ids: list[str] = []
        retryable_ids: list[str] = []
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
                (status_failed_permanent, "Lease expired", now_ts, exhausted_ids),
            )

        if retryable_ids:
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
                    status_failed_retry,
                    now_ts,
                    policy.base_seconds,
                    policy.max_seconds,
                    "Lease expired",
                    now_ts,
                    retryable_ids,
                ),
            )

    @staticmethod
    def mark_done(
        *,
        job_id: str,
        now_ts: int,
        status_done: str,
        status_processing: str,
        worker_id: str | None = None,
    ) -> int:
        ph = sql_placeholder()
        con = get_connection()
        try:
            cur = con.cursor()
            if worker_id:
                cur.execute(
                    f"""
                    UPDATE index_jobs
                    SET
                        status = {ph},
                        content = '',
                        title = '',
                        lease_until = NULL,
                        worker_id = NULL,
                        last_error = NULL,
                        updated_at = {ph}
                    WHERE job_id = {ph}
                      AND status = {ph}
                      AND worker_id = {ph}
                    """,
                    (status_done, now_ts, job_id, status_processing, worker_id),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE index_jobs
                    SET
                        status = {ph},
                        content = '',
                        title = '',
                        lease_until = NULL,
                        worker_id = NULL,
                        last_error = NULL,
                        updated_at = {ph}
                    WHERE job_id = {ph}
                    """,
                    (status_done, now_ts, job_id),
                )
            affected = cur.rowcount
            con.commit()
            cur.close()
            return affected
        finally:
            con.close()

    @staticmethod
    def fetch_retry_state(
        *,
        job_id: str,
        status_processing: str,
        worker_id: str | None = None,
    ) -> int | None:
        ph = sql_placeholder()
        con = get_connection()
        try:
            cur = con.cursor()
            if worker_id:
                cur.execute(
                    f"""
                    SELECT retry_count
                    FROM index_jobs
                    WHERE job_id = {ph} AND status = {ph} AND worker_id = {ph}
                    """,
                    (job_id, status_processing, worker_id),
                )
            else:
                cur.execute(
                    f"""
                    SELECT retry_count
                    FROM index_jobs
                    WHERE job_id = {ph}
                    """,
                    (job_id,),
                )
            row = cur.fetchone()
            cur.close()
            if not row:
                con.commit()
                return None
            con.commit()
            return int(row[0])
        finally:
            con.close()

    @staticmethod
    def mark_failed_permanent(
        *,
        job_id: str,
        retry_count: int,
        error_text: str,
        now_ts: int,
        status_failed_permanent: str,
    ) -> None:
        ph = sql_placeholder()
        con = get_connection()
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                UPDATE index_jobs
                SET
                    status = {ph},
                    retry_count = {ph},
                    lease_until = NULL,
                    worker_id = NULL,
                    last_error = {ph},
                    updated_at = {ph}
                WHERE job_id = {ph}
                """,
                (
                    status_failed_permanent,
                    retry_count,
                    error_text,
                    now_ts,
                    job_id,
                ),
            )
            con.commit()
            cur.close()
        finally:
            con.close()

    @staticmethod
    def mark_failed_retry(
        *,
        job_id: str,
        retry_count: int,
        available_at: int,
        error_text: str,
        now_ts: int,
        status_failed_retry: str,
    ) -> None:
        ph = sql_placeholder()
        con = get_connection()
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                UPDATE index_jobs
                SET
                    status = {ph},
                    retry_count = {ph},
                    available_at = {ph},
                    lease_until = NULL,
                    worker_id = NULL,
                    last_error = {ph},
                    updated_at = {ph}
                WHERE job_id = {ph}
                """,
                (
                    status_failed_retry,
                    retry_count,
                    available_at,
                    error_text,
                    now_ts,
                    job_id,
                ),
            )
            con.commit()
            cur.close()
        finally:
            con.close()

    @staticmethod
    def cleanup_old_done_jobs(*, now_ts: int, cutoff: int, status_done: str) -> int:
        ph = sql_placeholder()
        con = get_connection()
        try:
            cur = con.cursor()
            cur.execute(
                f"DELETE FROM index_jobs WHERE status = {ph} AND updated_at < {ph}",
                (status_done, cutoff),
            )
            deleted = cur.rowcount
            con.commit()
            cur.close()
            return deleted
        finally:
            con.close()
