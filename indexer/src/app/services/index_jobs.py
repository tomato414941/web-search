"""Indexer async job queue service."""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.metrics import record_claim_batch, record_job_result
from app.services.dedupe import build_dedupe_key, hash_text
from app.services.job_recovery import (
    cleanup_old_done_jobs,
    get_failed_permanent_jobs,
    recover_expired_locked,
    retry_failed_job,
)
from shared.core.retry import RetryPolicy
from shared.contracts.enums import CLAIMABLE_JOB_STATUSES, IndexJobStatus
from shared.postgres.search import get_connection, sql_placeholder

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
STATUS_PENDING = IndexJobStatus.PENDING
STATUS_PROCESSING = IndexJobStatus.PROCESSING
STATUS_DONE = IndexJobStatus.DONE
STATUS_FAILED_RETRY = IndexJobStatus.FAILED_RETRY
STATUS_FAILED_PERMANENT = IndexJobStatus.FAILED_PERMANENT

CLAIMABLE_STATUSES = CLAIMABLE_JOB_STATUSES


@dataclass(frozen=True)
class IndexJob:
    job_id: str
    url: str
    title: str
    content: str
    outlinks: list[str]
    status: str
    retry_count: int
    max_retries: int
    published_at: str | None = None
    updated_at: str | None = None
    author: str | None = None
    organization: str | None = None


class IndexJobService:
    def __init__(
        self,
        db_path: str,
        *,
        max_retries: int = 5,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 1800,
    ):
        self.db_path = db_path
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    @property
    def _retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.max_retries,
            base_delay=self.retry_base_seconds,
            max_delay=self.retry_max_seconds,
        )

    @staticmethod
    def _now_ts() -> int:
        return int(time.time())

    @staticmethod
    def _normalize_outlinks(outlinks: list[str] | None) -> list[str]:
        if not outlinks:
            return []
        normalized: list[str] = []
        for item in outlinks:
            if not item:
                continue
            normalized.append(str(item))
        return normalized

    @staticmethod
    def _decode_outlinks(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return []
            if isinstance(decoded, list):
                return [str(v) for v in decoded if v]
        return []

    def enqueue(
        self,
        *,
        url: str,
        title: str,
        content: str,
        outlinks: list[str] | None,
        published_at: str | None = None,
        updated_at: str | None = None,
        author: str | None = None,
        organization: str | None = None,
    ) -> tuple[str, bool]:
        """Queue a new indexing job (idempotent by dedupe_key)."""
        content_hash = hash_text(content)
        clean_outlinks = self._normalize_outlinks(outlinks)
        outlinks_hash = (
            hash_text("\n".join(sorted(clean_outlinks))) if clean_outlinks else ""
        )
        dedupe_key = build_dedupe_key(url, content_hash, outlinks_hash)
        job_id = str(uuid.uuid4())
        now_ts = self._now_ts()
        outlinks_json = json.dumps(clean_outlinks)
        max_retries = self.max_retries
        ph = sql_placeholder()

        # PG needs explicit JSONB cast for parameterized values
        jsonb_ph = f"{ph}::jsonb"

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                INSERT INTO index_jobs (
                    job_id, url, title, content, outlinks,
                    status, retry_count, max_retries,
                    available_at, lease_until, worker_id, last_error,
                    created_at, updated_at, content_hash, dedupe_key,
                    published_at, author, organization
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {jsonb_ph},
                    {ph}, 0, {ph},
                    {ph}, NULL, NULL, NULL,
                    {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}
                )
                ON CONFLICT (dedupe_key) DO NOTHING
                RETURNING job_id
                """,
                (
                    job_id,
                    url,
                    title,
                    content,
                    outlinks_json,
                    STATUS_PENDING,
                    max_retries,
                    now_ts,
                    now_ts,
                    now_ts,
                    content_hash,
                    dedupe_key,
                    published_at,
                    author,
                    organization,
                ),
            )
            row = cur.fetchone()
            if row:
                con.commit()
                cur.close()
                return str(row[0]), True

            cur.execute(
                f"SELECT job_id FROM index_jobs WHERE dedupe_key = {ph}",
                (dedupe_key,),
            )
            existing = cur.fetchone()
            con.commit()
            cur.close()
            if not existing:
                raise RuntimeError("Failed to resolve deduplicated index job")
            return str(existing[0]), False
        finally:
            con.close()

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                SELECT job_id, status, retry_count, max_retries, last_error,
                       available_at, created_at, updated_at
                FROM index_jobs
                WHERE job_id = {ph}
                """,
                (job_id,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return None
            return {
                "job_id": str(row[0]),
                "status": str(row[1]),
                "retry_count": int(row[2]),
                "max_retries": int(row[3]),
                "last_error": row[4],
                "available_at": int(row[5]) if row[5] is not None else None,
                "created_at": int(row[6]) if row[6] is not None else None,
                "updated_at": int(row[7]) if row[7] is not None else None,
            }
        finally:
            con.close()

    def claim_jobs(
        self,
        *,
        limit: int,
        lease_seconds: int,
        worker_id: str,
    ) -> list[IndexJob]:
        if limit <= 0:
            return []

        now_ts = self._now_ts()
        lease_until = now_ts + lease_seconds
        ph = sql_placeholder()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            recover_expired_locked(cur, now_ts, self._retry_policy)

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
                    j.outlinks, j.status, j.retry_count, j.max_retries,
                    j.published_at, j.author, j.organization
                """,
                (
                    STATUS_PENDING,
                    STATUS_FAILED_RETRY,
                    now_ts,
                    limit,
                    STATUS_PROCESSING,
                    lease_until,
                    worker_id,
                    now_ts,
                ),
            )
            rows = cur.fetchall()
            con.commit()
            cur.close()
            record_claim_batch(len(rows))
            return [self._row_to_job(row) for row in rows]
        finally:
            con.close()

    def mark_done(self, job_id: str, worker_id: str | None = None) -> bool:
        """Mark job as done. Returns True if update succeeded (CAS check)."""
        now_ts = self._now_ts()
        ph = sql_placeholder()

        con = get_connection(self.db_path)
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
                        outlinks = {ph},
                        lease_until = NULL,
                        worker_id = NULL,
                        last_error = NULL,
                        updated_at = {ph}
                    WHERE job_id = {ph}
                      AND status = {ph}
                      AND worker_id = {ph}
                    """,
                    (STATUS_DONE, "[]", now_ts, job_id, STATUS_PROCESSING, worker_id),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE index_jobs
                    SET
                        status = {ph},
                        content = '',
                        title = '',
                        outlinks = {ph},
                        lease_until = NULL,
                        worker_id = NULL,
                        last_error = NULL,
                        updated_at = {ph}
                    WHERE job_id = {ph}
                    """,
                    (STATUS_DONE, "[]", now_ts, job_id),
                )
            affected = cur.rowcount
            con.commit()
            cur.close()
            if affected == 0 and worker_id:
                logger.warning(
                    "mark_done lost update: job=%s worker=%s", job_id, worker_id
                )
            if affected > 0:
                record_job_result(STATUS_DONE)
            return affected > 0
        finally:
            con.close()

    def mark_failure(
        self, job_id: str, error_text: str, worker_id: str | None = None
    ) -> bool:
        """Mark job as failed (retry or permanent). Returns True if update succeeded."""
        now_ts = self._now_ts()
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            if worker_id:
                cur.execute(
                    f"""
                    SELECT retry_count, max_retries
                    FROM index_jobs
                    WHERE job_id = {ph} AND status = {ph} AND worker_id = {ph}
                    """,
                    (job_id, STATUS_PROCESSING, worker_id),
                )
            else:
                cur.execute(
                    f"""
                    SELECT retry_count, max_retries
                    FROM index_jobs
                    WHERE job_id = {ph}
                    """,
                    (job_id,),
                )
            row = cur.fetchone()
            if not row:
                con.commit()
                cur.close()
                if worker_id:
                    logger.warning(
                        "mark_failure lost update: job=%s worker=%s",
                        job_id,
                        worker_id,
                    )
                return False

            retry_count = int(row[0]) + 1
            policy = self._retry_policy
            if policy.is_exhausted(retry_count):
                result_status = STATUS_FAILED_PERMANENT
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
                        result_status,
                        retry_count,
                        error_text,
                        now_ts,
                        job_id,
                    ),
                )
            else:
                result_status = STATUS_FAILED_RETRY
                available_at = now_ts + policy.delay_seconds(retry_count)
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
                        result_status,
                        retry_count,
                        available_at,
                        error_text,
                        now_ts,
                        job_id,
                    ),
                )
            con.commit()
            cur.close()
            record_job_result(result_status)
            return True
        finally:
            con.close()

    def get_queue_stats(self) -> dict[str, int]:
        """Return lightweight queue stats using indexed status lookups."""
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            ph = sql_placeholder()
            cur.execute(
                f"""
                SELECT status, COUNT(*) FROM index_jobs
                WHERE status IN ({ph}, {ph}, {ph}, {ph})
                GROUP BY status
                """,
                (
                    STATUS_PENDING,
                    STATUS_FAILED_RETRY,
                    STATUS_PROCESSING,
                    STATUS_FAILED_PERMANENT,
                ),
            )
            counts: dict[str, int] = {}
            for status, count in cur.fetchall():
                counts[status] = int(count)
            cur.close()

            pending = counts.get(STATUS_PENDING, 0) + counts.get(STATUS_FAILED_RETRY, 0)
            return {
                "pending_jobs": pending,
                "processing_jobs": counts.get(STATUS_PROCESSING, 0),
                "failed_permanent_jobs": counts.get(STATUS_FAILED_PERMANENT, 0),
            }
        finally:
            con.close()

    def cleanup_old_done_jobs(self, max_age_seconds: int = 7 * 86400) -> int:
        """Delete completed jobs older than max_age_seconds. Returns deleted count."""
        return cleanup_old_done_jobs(self.db_path, self._now_ts(), max_age_seconds)

    def get_failed_permanent_jobs(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return failed_permanent jobs for admin visibility."""
        return get_failed_permanent_jobs(self.db_path, limit=limit, offset=offset)

    def retry_failed_job(self, job_id: str) -> bool:
        """Reset a failed_permanent job back to pending. Returns True if reset."""
        return retry_failed_job(self.db_path, job_id, self._now_ts())

    def _row_to_job(self, row: tuple[Any, ...]) -> IndexJob:
        return IndexJob(
            job_id=str(row[0]),
            url=str(row[1]),
            title=str(row[2]),
            content=str(row[3]),
            outlinks=self._decode_outlinks(row[4]),
            status=str(row[5]),
            retry_count=int(row[6]),
            max_retries=int(row[7]),
            published_at=str(row[8]) if len(row) > 8 and row[8] else None,
            author=str(row[9]) if len(row) > 9 and row[9] else None,
            organization=str(row[10]) if len(row) > 10 and row[10] else None,
        )
