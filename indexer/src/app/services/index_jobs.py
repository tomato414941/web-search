"""Indexer async job queue service."""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from shared.db.search import get_connection, is_postgres_mode, sql_placeholder

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED_RETRY = "failed_retry"
STATUS_FAILED_PERMANENT = "failed_permanent"

CLAIMABLE_STATUSES = (STATUS_PENDING, STATUS_FAILED_RETRY)


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

    @staticmethod
    def _now_ts() -> int:
        return int(time.time())

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _build_dedupe_key(cls, url: str, content_hash: str) -> str:
        return cls._hash_text(f"{url}\n{content_hash}")

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
    ) -> tuple[str, bool]:
        """Queue a new indexing job (idempotent by dedupe_key)."""
        content_hash = self._hash_text(content)
        dedupe_key = self._build_dedupe_key(url, content_hash)
        job_id = str(uuid.uuid4())
        now_ts = self._now_ts()
        clean_outlinks = self._normalize_outlinks(outlinks)
        outlinks_json = json.dumps(clean_outlinks)
        max_retries = self.max_retries
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            if is_postgres_mode():
                cur.execute(
                    f"""
                    INSERT INTO index_jobs (
                        job_id, url, title, content, outlinks,
                        status, retry_count, max_retries,
                        available_at, lease_until, worker_id, last_error,
                        created_at, updated_at, content_hash, dedupe_key
                    ) VALUES (
                        {ph}, {ph}, {ph}, {ph}, {ph}::jsonb,
                        {ph}, 0, {ph},
                        {ph}, NULL, NULL, NULL,
                        {ph}, {ph}, {ph}, {ph}
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

            cur.execute(
                f"""
                INSERT OR IGNORE INTO index_jobs (
                    job_id, url, title, content, outlinks,
                    status, retry_count, max_retries,
                    available_at, lease_until, worker_id, last_error,
                    created_at, updated_at, content_hash, dedupe_key
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, 0, {ph},
                    {ph}, NULL, NULL, NULL,
                    {ph}, {ph}, {ph}, {ph}
                )
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
                ),
            )
            inserted = cur.rowcount > 0
            if inserted:
                con.commit()
                cur.close()
                return job_id, True

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
            self._recover_expired_locked(cur, now_ts)

            if is_postgres_mode():
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
                        j.outlinks, j.status, j.retry_count, j.max_retries
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
                return [self._row_to_job(row) for row in rows]

            cur.execute(
                f"""
                SELECT job_id
                FROM index_jobs
                WHERE status IN ({ph}, {ph}) AND available_at <= {ph}
                ORDER BY available_at ASC, created_at ASC
                LIMIT {ph}
                """,
                (STATUS_PENDING, STATUS_FAILED_RETRY, now_ts, limit),
            )
            ids = [str(row[0]) for row in cur.fetchall()]
            if not ids:
                con.commit()
                cur.close()
                return []

            id_placeholders = ",".join([ph] * len(ids))
            cur.execute(
                f"""
                UPDATE index_jobs
                SET
                    status = {ph},
                    lease_until = {ph},
                    worker_id = {ph},
                    updated_at = {ph}
                WHERE job_id IN ({id_placeholders})
                """,
                (STATUS_PROCESSING, lease_until, worker_id, now_ts, *ids),
            )

            cur.execute(
                f"""
                SELECT
                    job_id, url, title, content,
                    outlinks, status, retry_count, max_retries
                FROM index_jobs
                WHERE job_id IN ({id_placeholders})
                """,
                tuple(ids),
            )
            rows = cur.fetchall()
            con.commit()
            cur.close()
            return [self._row_to_job(row) for row in rows]
        finally:
            con.close()

    def mark_done(self, job_id: str) -> None:
        now_ts = self._now_ts()
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                f"""
                UPDATE index_jobs
                SET
                    status = {ph},
                    lease_until = NULL,
                    worker_id = NULL,
                    last_error = NULL,
                    updated_at = {ph}
                WHERE job_id = {ph}
                """,
                (STATUS_DONE, now_ts, job_id),
            )
            con.commit()
            cur.close()
        finally:
            con.close()

    def mark_failure(self, job_id: str, error_text: str) -> None:
        now_ts = self._now_ts()
        ph = sql_placeholder()

        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
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
                return

            retry_count = int(row[0]) + 1
            max_retries = int(row[1])
            if retry_count >= max_retries:
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
                        STATUS_FAILED_PERMANENT,
                        retry_count,
                        error_text,
                        now_ts,
                        job_id,
                    ),
                )
            else:
                available_at = now_ts + self._retry_delay_seconds(retry_count)
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
                        STATUS_FAILED_RETRY,
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

    def get_queue_stats(self) -> dict[str, int]:
        now_ts = self._now_ts()
        con = get_connection(self.db_path)
        try:
            cur = con.cursor()
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                    SUM(CASE WHEN status = 'failed_retry' THEN 1 ELSE 0 END) AS retry_count,
                    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) AS processing_count,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done_count,
                    SUM(CASE WHEN status = 'failed_permanent' THEN 1 ELSE 0 END) AS failed_permanent_count,
                    COUNT(*) AS total_count
                FROM index_jobs
                """
            )
            row = cur.fetchone()

            ph = sql_placeholder()
            cur.execute(
                f"""
                SELECT MIN(available_at)
                FROM index_jobs
                WHERE status IN ({ph}, {ph})
                """,
                (STATUS_PENDING, STATUS_FAILED_RETRY),
            )
            min_available = cur.fetchone()[0]
            cur.close()

            pending_count = int((row[0] or 0) + (row[1] or 0))
            oldest_pending_seconds = 0
            if min_available is not None:
                oldest_pending_seconds = max(0, now_ts - int(min_available))

            return {
                "pending_jobs": pending_count,
                "processing_jobs": int(row[2] or 0),
                "done_jobs": int(row[3] or 0),
                "failed_permanent_jobs": int(row[4] or 0),
                "total_jobs": int(row[5] or 0),
                "oldest_pending_seconds": oldest_pending_seconds,
            }
        finally:
            con.close()

    def _retry_delay_seconds(self, retry_count: int) -> int:
        # retry_count is already incremented (1, 2, 3...).
        raw = self.retry_base_seconds * (2 ** (retry_count - 1))
        return min(raw, self.retry_max_seconds)

    def _recover_expired_locked(self, cur: Any, now_ts: int) -> None:
        ph = sql_placeholder()
        cur.execute(
            f"""
            SELECT job_id, retry_count, max_retries
            FROM index_jobs
            WHERE status = {ph}
              AND lease_until IS NOT NULL
              AND lease_until < {ph}
            """,
            (STATUS_PROCESSING, now_ts),
        )
        expired = cur.fetchall()
        for job_id, retry_count, max_retries in expired:
            next_retry = int(retry_count) + 1
            if next_retry >= int(max_retries):
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
                        STATUS_FAILED_PERMANENT,
                        next_retry,
                        "Lease expired",
                        now_ts,
                        job_id,
                    ),
                )
            else:
                available_at = now_ts + self._retry_delay_seconds(next_retry)
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
                        STATUS_FAILED_RETRY,
                        next_retry,
                        available_at,
                        "Lease expired",
                        now_ts,
                        job_id,
                    ),
                )

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
        )
