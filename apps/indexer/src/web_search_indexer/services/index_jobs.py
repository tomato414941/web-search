"""Indexer async job queue service."""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from web_search_indexer.metrics import record_claim_batch, record_job_result
from web_search_indexer.services.dedupe import build_dedupe_key, hash_text
from web_search_indexer.services.job_recovery import (
    cleanup_old_done_jobs,
)
from web_search_core.retry import RetryPolicy
from web_search_contracts.enums import CLAIMABLE_JOB_STATUSES, IndexJobStatus
from web_search_postgres.repositories.index_job_repo import IndexJobRepository

logger = logging.getLogger(__name__)

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
        max_retries: int = 5,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 1800,
    ):
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
        del updated_at
        content_hash = hash_text(content)
        clean_outlinks = self._normalize_outlinks(outlinks)
        outlinks_hash = (
            hash_text("\n".join(sorted(clean_outlinks))) if clean_outlinks else ""
        )
        dedupe_key = build_dedupe_key(url, content_hash, outlinks_hash)
        return IndexJobRepository.enqueue(
            job_id=str(uuid.uuid4()),
            url=url,
            title=title,
            content=content,
            outlinks_json=json.dumps(clean_outlinks),
            status_pending=STATUS_PENDING,
            max_retries=self.max_retries,
            now_ts=self._now_ts(),
            content_hash=content_hash,
            dedupe_key=dedupe_key,
            published_at=published_at,
            author=author,
            organization=organization,
        )

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        row = IndexJobRepository.fetch_status(job_id)
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
        rows = IndexJobRepository.claim_jobs(
            now_ts=now_ts,
            lease_until=now_ts + lease_seconds,
            limit=limit,
            worker_id=worker_id,
            status_pending=STATUS_PENDING,
            status_failed_retry=STATUS_FAILED_RETRY,
            status_failed_permanent=STATUS_FAILED_PERMANENT,
            status_processing=STATUS_PROCESSING,
            policy=self._retry_policy,
        )
        record_claim_batch(len(rows))
        return [self._row_to_job(row) for row in rows]

    def mark_done(self, job_id: str, worker_id: str | None = None) -> bool:
        """Mark job as done. Returns True if update succeeded (CAS check)."""
        affected = IndexJobRepository.mark_done(
            job_id=job_id,
            now_ts=self._now_ts(),
            status_done=STATUS_DONE,
            status_processing=STATUS_PROCESSING,
            worker_id=worker_id,
        )
        if affected == 0 and worker_id:
            logger.warning("mark_done lost update: job=%s worker=%s", job_id, worker_id)
        if affected > 0:
            record_job_result(STATUS_DONE)
        return affected > 0

    def mark_failure(
        self, job_id: str, error_text: str, worker_id: str | None = None
    ) -> bool:
        """Mark job as failed (retry or permanent). Returns True if update succeeded."""
        row = IndexJobRepository.fetch_retry_state(
            job_id=job_id,
            status_processing=STATUS_PROCESSING,
            worker_id=worker_id,
        )
        if not row:
            if worker_id:
                logger.warning(
                    "mark_failure lost update: job=%s worker=%s",
                    job_id,
                    worker_id,
                )
            return False

        retry_count = int(row[0]) + 1
        policy = self._retry_policy
        now_ts = self._now_ts()
        if policy.is_exhausted(retry_count):
            result_status = STATUS_FAILED_PERMANENT
            IndexJobRepository.mark_failed_permanent(
                job_id=job_id,
                retry_count=retry_count,
                error_text=error_text,
                now_ts=now_ts,
                status_failed_permanent=result_status,
            )
        else:
            result_status = STATUS_FAILED_RETRY
            IndexJobRepository.mark_failed_retry(
                job_id=job_id,
                retry_count=retry_count,
                available_at=now_ts + policy.delay_seconds(retry_count),
                error_text=error_text,
                now_ts=now_ts,
                status_failed_retry=result_status,
            )
        record_job_result(result_status)
        return True

    def cleanup_old_done_jobs(self, max_age_seconds: int = 7 * 86400) -> int:
        """Delete completed jobs older than max_age_seconds. Returns deleted count."""
        return cleanup_old_done_jobs(self._now_ts(), max_age_seconds)

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
