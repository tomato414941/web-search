import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import partial
import logging
import os
import signal
import sys
import time
from typing import Any, Literal, cast

from web_search_indexer.core.config import settings
from web_search_indexer.metrics import (
    maybe_start_worker_metrics_server,
    record_cleanup_deleted,
    record_job_processing_duration,
    record_maintenance_run,
    record_worker_error,
    record_worker_start,
)
from web_search_indexer.services.index_job_container import (
    configure_index_job_service,
    index_job_service,
)
from web_search_indexer.services.indexer import IndexedPage, indexer_service
from web_search_postgres.migrate import migrate
from web_search_indexer.services.pagerank import (
    calculate_domain_pagerank,
    calculate_pagerank,
)

logger = logging.getLogger(__name__)
WorkerMode = Literal["all", "jobs", "maintenance"]
TaskFactory = Callable[[], Awaitable[None]]
TaskSpec = tuple[str, TaskFactory]


@dataclass(slots=True)
class ProcessedJob:
    job_id: str
    page: IndexedPage


async def _pagerank_loop() -> None:
    interval = settings.PAGERANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = await asyncio.to_thread(calculate_pagerank)
            record_maintenance_run("pagerank", success=True)
            logger.info("Page PageRank recalculated: %s pages", count)
        except Exception:
            record_maintenance_run("pagerank", success=False)
            record_worker_error("pagerank")
            logger.exception("Page PageRank calculation failed")


async def _job_cleanup_loop() -> None:
    cleanup_interval = int(os.getenv("JOB_CLEANUP_INTERVAL_HOURS", "6")) * 3600
    max_age = int(os.getenv("JOB_CLEANUP_MAX_AGE_DAYS", "7")) * 86400
    while True:
        await asyncio.sleep(cleanup_interval)
        try:
            deleted = await asyncio.to_thread(
                index_job_service.cleanup_old_done_jobs, max_age
            )
            record_cleanup_deleted(deleted)
            record_maintenance_run("job_cleanup", success=True)
            logger.info("Job cleanup: deleted %d old done jobs", deleted)
        except Exception:
            record_maintenance_run("job_cleanup", success=False)
            record_worker_error("job_cleanup")
            logger.exception("Job cleanup failed")


async def _domain_rank_loop() -> None:
    interval = settings.DOMAIN_RANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = await asyncio.to_thread(calculate_domain_pagerank)
            record_maintenance_run("domain_rank", success=True)
            logger.info("Domain PageRank recalculated: %s domains", count)
        except Exception:
            record_maintenance_run("domain_rank", success=False)
            record_worker_error("domain_rank")
            logger.exception("Domain PageRank calculation failed")


async def _process_single_job(
    job: Any,
    worker_name: str,
    semaphore: asyncio.Semaphore,
) -> ProcessedJob | None:
    """Process a single index job."""
    async with semaphore:
        started_at = time.monotonic()
        try:
            page = await indexer_service.index_page(
                url=job.url,
                title=job.title,
                content=job.content,
                outlinks_count=job.outlinks_count,
                published_at=job.published_at,
                author=job.author,
                organization=job.organization,
                skip_opensearch=True,
            )
            return ProcessedJob(
                job_id=job.job_id,
                page=page,
            )
        except Exception as exc:
            error_text = str(exc)
            logger.exception(
                "%s failed job %s (%s): %s",
                worker_name,
                job.job_id,
                job.url,
                error_text,
            )
            await asyncio.to_thread(
                index_job_service.mark_failure,
                job.job_id,
                error_text,
                worker_id=worker_name,
            )
        finally:
            record_job_processing_duration(time.monotonic() - started_at)
    return None


async def _index_job_worker_loop(worker_name: str) -> None:
    poll_interval = max(settings.INDEXER_JOB_POLL_INTERVAL_MS, 50) / 1000.0
    semaphore = asyncio.Semaphore(settings.INDEXER_JOB_CONCURRENCY)

    while True:
        try:
            jobs = await asyncio.to_thread(
                index_job_service.claim_jobs,
                limit=settings.INDEXER_JOB_BATCH_SIZE,
                lease_seconds=settings.INDEXER_JOB_LEASE_SEC,
                worker_id=worker_name,
            )
        except Exception:
            record_worker_error("claim_jobs")
            logger.exception("%s failed to claim jobs", worker_name)
            await asyncio.sleep(poll_interval)
            continue

        if not jobs:
            await asyncio.sleep(poll_interval)
            continue

        processed_jobs = [
            result
            for result in await asyncio.gather(
                *[
                    _process_single_job(
                        job,
                        worker_name,
                        semaphore,
                    )
                    for job in jobs
                ]
            )
            if result is not None
        ]

        if not processed_jobs:
            continue

        try:
            await indexer_service.index_pages_to_opensearch(
                [processed.page for processed in processed_jobs]
            )
        except Exception as exc:
            record_worker_error("batch_opensearch")
            logger.exception(
                "%s batch OpenSearch indexing failed for %d items",
                worker_name,
                len(processed_jobs),
            )
            error_text = f"OpenSearch indexing failed: {exc}"
            for processed in processed_jobs:
                await asyncio.to_thread(
                    index_job_service.mark_failure,
                    processed.job_id,
                    error_text,
                    worker_id=worker_name,
                )
            continue

        for processed in processed_jobs:
            await asyncio.to_thread(
                index_job_service.mark_done,
                processed.job_id,
                worker_id=worker_name,
            )


def resolve_worker_mode(argv: Sequence[str]) -> WorkerMode:
    if len(argv) < 2:
        return "all"

    mode = argv[1].strip().lower()
    if mode not in {"all", "jobs", "maintenance"}:
        raise ValueError(
            f"Unsupported worker mode '{argv[1]}'. Expected: all, jobs, maintenance"
        )
    return cast(WorkerMode, mode)


def _build_task_specs(mode: WorkerMode) -> list[TaskSpec]:
    task_specs: list[TaskSpec] = []

    if mode in {"all", "maintenance"}:
        task_specs.extend(
            [
                ("pagerank", _pagerank_loop),
                ("domain-rank", _domain_rank_loop),
                ("job-cleanup", _job_cleanup_loop),
            ]
        )

    if mode in {"all", "jobs"}:
        for i in range(max(1, settings.INDEXER_JOB_WORKERS)):
            worker_name = f"indexer-worker-{i + 1}"
            task_specs.append(
                (worker_name, partial(_index_job_worker_loop, worker_name))
            )

    return task_specs


async def main(mode: WorkerMode = "all") -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting indexer worker mode=%s", mode)
    record_worker_start(mode)
    metrics_port = maybe_start_worker_metrics_server()
    if metrics_port is not None:
        logger.info("Worker metrics server started on port %s", metrics_port)

    if settings.RUN_MIGRATIONS:
        migrate()

    configure_index_job_service()

    task_specs = _build_task_specs(mode)
    tasks = [
        asyncio.create_task(task_factory(), name=task_name)
        for task_name, task_factory in task_specs
    ]

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: stop_event.set())

    await stop_event.wait()
    logger.info("Shutdown requested, cancelling %d worker tasks", len(tasks))
    for task in tasks:
        task.cancel()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for task_name, result in zip(
        (name for name, _ in task_specs), results, strict=False
    ):
        if isinstance(result, asyncio.CancelledError):
            continue
        if isinstance(result, Exception):
            logger.exception("Task %s exited with error", task_name, exc_info=result)


if __name__ == "__main__":
    try:
        worker_mode = resolve_worker_mode(sys.argv)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    asyncio.run(main(worker_mode))
