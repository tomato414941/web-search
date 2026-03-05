import logging
import os

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

logger = logging.getLogger(__name__)

router = APIRouter()

INDEXER_INDEXED_PAGES = Gauge(
    "indexer_indexed_pages",
    "Number of indexed pages stored in documents",
)
INDEXER_QUEUE_PENDING = Gauge(
    "indexer_queue_pending_jobs",
    "Number of queued jobs waiting to be processed",
)
INDEXER_QUEUE_PROCESSING = Gauge(
    "indexer_queue_processing_jobs",
    "Number of jobs currently being processed",
)
INDEXER_QUEUE_DONE = Gauge(
    "indexer_queue_done_jobs",
    "Number of completed jobs retained in the queue table",
)
INDEXER_QUEUE_FAILED_PERMANENT = Gauge(
    "indexer_queue_failed_permanent_jobs",
    "Number of permanently failed jobs",
)
INDEXER_QUEUE_TOTAL = Gauge(
    "indexer_queue_total_jobs",
    "Total number of jobs retained in the queue table",
)
INDEXER_QUEUE_OLDEST_PENDING = Gauge(
    "indexer_queue_oldest_pending_seconds",
    "Age in seconds of the oldest claimable job",
)

INDEXER_JOB_CLAIMS_TOTAL = Counter(
    "indexer_worker_job_claims_total",
    "Total number of jobs claimed by worker loops",
)
INDEXER_JOB_CLAIM_BATCH_SIZE = Histogram(
    "indexer_worker_claim_batch_size",
    "Number of jobs claimed in one polling cycle",
    buckets=[0, 1, 2, 5, 10, 20, 50, 100],
)
INDEXER_JOB_RESULTS_TOTAL = Counter(
    "indexer_worker_job_results_total",
    "Total number of worker job transitions",
    ["result"],
)
INDEXER_JOB_PROCESSING_SECONDS = Histogram(
    "indexer_worker_job_processing_seconds",
    "Wall-clock time spent processing a single job",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
INDEXER_BATCH_EMBEDDING_ITEMS = Histogram(
    "indexer_worker_batch_embedding_items",
    "Number of deferred embeddings sent in a batch",
    buckets=[0, 1, 2, 5, 10, 20, 50, 100],
)
INDEXER_BATCH_EMBEDDING_SECONDS = Histogram(
    "indexer_worker_batch_embedding_seconds",
    "Wall-clock time spent embedding one batch",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
INDEXER_BATCH_EMBEDDING_FAILURES_TOTAL = Counter(
    "indexer_worker_batch_embedding_failures_total",
    "Number of batch embedding failures",
)
INDEXER_WORKER_ERRORS_TOTAL = Counter(
    "indexer_worker_errors_total",
    "Number of worker loop errors by stage",
    ["stage"],
)
INDEXER_WORKER_STARTS_TOTAL = Counter(
    "indexer_worker_starts_total",
    "Number of worker process starts by mode",
    ["mode"],
)
INDEXER_MAINTENANCE_RUNS_TOTAL = Counter(
    "indexer_maintenance_runs_total",
    "Number of maintenance loop runs",
    ["task", "status"],
)
INDEXER_JOB_CLEANUP_DELETED_TOTAL = Counter(
    "indexer_job_cleanup_deleted_total",
    "Total number of old done jobs deleted by cleanup",
)


def update_queue_metrics(queue_stats: dict[str, int]) -> None:
    INDEXER_QUEUE_PENDING.set(queue_stats.get("pending_jobs", 0))
    INDEXER_QUEUE_PROCESSING.set(queue_stats.get("processing_jobs", 0))
    INDEXER_QUEUE_DONE.set(queue_stats.get("done_jobs", 0))
    INDEXER_QUEUE_FAILED_PERMANENT.set(queue_stats.get("failed_permanent_jobs", 0))
    INDEXER_QUEUE_TOTAL.set(queue_stats.get("total_jobs", 0))
    INDEXER_QUEUE_OLDEST_PENDING.set(queue_stats.get("oldest_pending_seconds", 0))


def update_indexed_pages_metric(indexed_pages: int) -> None:
    INDEXER_INDEXED_PAGES.set(indexed_pages)


def record_claim_batch(claimed_jobs: int) -> None:
    INDEXER_JOB_CLAIM_BATCH_SIZE.observe(claimed_jobs)
    if claimed_jobs > 0:
        INDEXER_JOB_CLAIMS_TOTAL.inc(claimed_jobs)


def record_job_result(result: str) -> None:
    INDEXER_JOB_RESULTS_TOTAL.labels(result=result).inc()


def record_job_processing_duration(duration_seconds: float) -> None:
    INDEXER_JOB_PROCESSING_SECONDS.observe(duration_seconds)


def record_batch_embedding(batch_size: int, duration_seconds: float) -> None:
    INDEXER_BATCH_EMBEDDING_ITEMS.observe(batch_size)
    INDEXER_BATCH_EMBEDDING_SECONDS.observe(duration_seconds)


def record_batch_embedding_failure() -> None:
    INDEXER_BATCH_EMBEDDING_FAILURES_TOTAL.inc()


def record_worker_error(stage: str) -> None:
    INDEXER_WORKER_ERRORS_TOTAL.labels(stage=stage).inc()


def record_worker_start(mode: str) -> None:
    INDEXER_WORKER_STARTS_TOTAL.labels(mode=mode).inc()


def record_maintenance_run(task: str, *, success: bool) -> None:
    status = "success" if success else "failure"
    INDEXER_MAINTENANCE_RUNS_TOTAL.labels(task=task, status=status).inc()


def record_cleanup_deleted(deleted_jobs: int) -> None:
    if deleted_jobs > 0:
        INDEXER_JOB_CLEANUP_DELETED_TOTAL.inc(deleted_jobs)


def maybe_start_worker_metrics_server() -> int | None:
    port = int(os.getenv("WORKER_METRICS_PORT", "9000"))
    if port <= 0:
        return None
    try:
        start_http_server(port)
        return port
    except OSError:
        logger.exception("Failed to start worker metrics server on port %s", port)
        return None


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
