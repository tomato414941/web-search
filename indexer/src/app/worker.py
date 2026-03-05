import asyncio
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
import logging
import os
import signal
import sys
import time
from typing import Any, Literal, cast

from app.api.routes import indexer
from app.core.config import settings
from app.metrics import (
    maybe_start_worker_metrics_server,
    record_batch_embedding,
    record_batch_embedding_failure,
    record_cleanup_deleted,
    record_job_processing_duration,
    record_maintenance_run,
    record_worker_error,
    record_worker_start,
)
from app.services.indexer import indexer_service
from shared.postgres.migrate import migrate
from shared.search_kernel.pagerank import calculate_domain_pagerank, calculate_pagerank

logger = logging.getLogger(__name__)
WorkerMode = Literal["all", "jobs", "maintenance"]
TaskFactory = Callable[[], Awaitable[None]]
TaskSpec = tuple[str, TaskFactory]


async def _pagerank_loop() -> None:
    interval = settings.PAGERANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = await asyncio.to_thread(calculate_pagerank, settings.DB_PATH)
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
                indexer.index_job_service.cleanup_old_done_jobs, max_age
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
            count = await asyncio.to_thread(calculate_domain_pagerank, settings.DB_PATH)
            record_maintenance_run("domain_rank", success=True)
            logger.info("Domain PageRank recalculated: %s domains", count)
        except Exception:
            record_maintenance_run("domain_rank", success=False)
            record_worker_error("domain_rank")
            logger.exception("Domain PageRank calculation failed")


async def _queue_metrics_loop() -> None:
    interval = max(1, int(os.getenv("QUEUE_METRICS_INTERVAL_SEC", "5")))
    while True:
        try:
            await asyncio.to_thread(indexer.index_job_service.get_queue_stats)
        except Exception:
            record_worker_error("queue_metrics")
            logger.exception("Queue metrics refresh failed")
        await asyncio.sleep(interval)


async def _process_single_job(
    job: Any,
    worker_name: str,
    use_batch_embed: bool,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str, str] | None:
    """Process a single index job.

    Returns (job_id, url, content) when batch embedding is deferred,
    or None when done immediately or on failure.
    """
    async with semaphore:
        started_at = time.monotonic()
        try:
            await indexer_service.index_page(
                url=job.url,
                title=job.title,
                content=job.content,
                outlinks=job.outlinks,
                published_at=job.published_at,
                author=job.author,
                organization=job.organization,
                skip_embedding=use_batch_embed,
            )
            if use_batch_embed and job.content:
                # Defer mark_done until after batch embedding succeeds
                return (job.job_id, job.url, job.content)
            await asyncio.to_thread(
                indexer.index_job_service.mark_done,
                job.job_id,
                worker_id=worker_name,
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
                indexer.index_job_service.mark_failure,
                job.job_id,
                error_text,
                worker_id=worker_name,
            )
        finally:
            record_job_processing_duration(time.monotonic() - started_at)
    return None


async def _index_job_worker_loop(worker_name: str) -> None:
    poll_interval = max(settings.INDEXER_JOB_POLL_INTERVAL_MS, 50) / 1000.0
    use_batch_embed = bool(settings.OPENAI_API_KEY)
    semaphore = asyncio.Semaphore(settings.INDEXER_JOB_CONCURRENCY)

    while True:
        try:
            jobs = await asyncio.to_thread(
                indexer.index_job_service.claim_jobs,
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

        # Process jobs concurrently with semaphore-limited parallelism
        results = await asyncio.gather(
            *[
                _process_single_job(job, worker_name, use_batch_embed, semaphore)
                for job in jobs
            ]
        )
        embed_items = [r for r in results if r is not None]

        # Batch embed all successful pages at once, then mark done
        if embed_items:
            job_ids = [r[0] for r in embed_items]
            url_content_pairs = [(r[1], r[2]) for r in embed_items]
            batch_started_at = time.monotonic()
            try:
                await indexer_service.embed_and_save_batch(url_content_pairs)
                record_batch_embedding(
                    len(url_content_pairs), time.monotonic() - batch_started_at
                )
                for jid in job_ids:
                    await asyncio.to_thread(
                        indexer.index_job_service.mark_done,
                        jid,
                        worker_id=worker_name,
                    )
            except Exception:
                record_batch_embedding_failure()
                record_worker_error("batch_embedding")
                logger.exception(
                    "%s batch embedding failed for %d items, marking as failure",
                    worker_name,
                    len(embed_items),
                )
                for jid in job_ids:
                    await asyncio.to_thread(
                        indexer.index_job_service.mark_failure,
                        jid,
                        "Batch embedding failed",
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


def _configure_index_job_service() -> None:
    indexer.index_job_service.db_path = settings.DB_PATH
    indexer.index_job_service.max_retries = settings.INDEXER_JOB_MAX_RETRIES
    indexer.index_job_service.retry_base_seconds = settings.INDEXER_JOB_RETRY_BASE_SEC
    indexer.index_job_service.retry_max_seconds = settings.INDEXER_JOB_RETRY_MAX_SEC


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
        task_specs.append(("queue-metrics", _queue_metrics_loop))
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

    _configure_index_job_service()

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
            signal.signal(sig, lambda *_: stop_event.set())

    await stop_event.wait()

    logger.info("Shutting down indexer worker mode=%s", mode)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        worker_mode = resolve_worker_mode(sys.argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    asyncio.run(main(worker_mode))
