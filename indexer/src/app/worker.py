import asyncio
import logging
import os
import signal
from typing import Any

from app.api.routes import indexer
from app.core.config import settings
from app.services.indexer import indexer_service
from shared.postgres.migrate import migrate
from shared.search_kernel.pagerank import calculate_domain_pagerank, calculate_pagerank

logger = logging.getLogger(__name__)


async def _pagerank_loop() -> None:
    interval = settings.PAGERANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = calculate_pagerank(settings.DB_PATH)
            logger.info("Page PageRank recalculated: %s pages", count)
        except Exception:
            logger.exception("Page PageRank calculation failed")


async def _job_cleanup_loop() -> None:
    cleanup_interval = int(os.getenv("JOB_CLEANUP_INTERVAL_HOURS", "6")) * 3600
    max_age = int(os.getenv("JOB_CLEANUP_MAX_AGE_DAYS", "7")) * 86400
    while True:
        await asyncio.sleep(cleanup_interval)
        try:
            deleted = indexer.index_job_service.cleanup_old_done_jobs(max_age)
            logger.info("Job cleanup: deleted %d old done jobs", deleted)
        except Exception:
            logger.exception("Job cleanup failed")


async def _domain_rank_loop() -> None:
    interval = settings.DOMAIN_RANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = calculate_domain_pagerank(settings.DB_PATH)
            logger.info("Domain PageRank recalculated: %s domains", count)
        except Exception:
            logger.exception("Domain PageRank calculation failed")


async def _process_single_job(
    job: Any,
    worker_name: str,
    use_batch_embed: bool,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str] | None:
    """Process a single index job. Returns (url, content) for batch embedding on success."""
    async with semaphore:
        try:
            await indexer_service.index_page(
                url=job.url,
                title=job.title,
                content=job.content,
                outlinks=job.outlinks,
                skip_embedding=use_batch_embed,
            )
            indexer.index_job_service.mark_done(job.job_id)
            if use_batch_embed and job.content:
                return (job.url, job.content)
        except Exception as exc:
            error_text = str(exc)
            logger.exception(
                "%s failed job %s (%s): %s",
                worker_name,
                job.job_id,
                job.url,
                error_text,
            )
            indexer.index_job_service.mark_failure(job.job_id, error_text)
    return None


async def _index_job_worker_loop(worker_name: str) -> None:
    poll_interval = max(settings.INDEXER_JOB_POLL_INTERVAL_MS, 50) / 1000.0
    use_batch_embed = bool(settings.OPENAI_API_KEY)
    semaphore = asyncio.Semaphore(settings.INDEXER_JOB_CONCURRENCY)

    while True:
        try:
            jobs = indexer.index_job_service.claim_jobs(
                limit=settings.INDEXER_JOB_BATCH_SIZE,
                lease_seconds=settings.INDEXER_JOB_LEASE_SEC,
                worker_id=worker_name,
            )
        except Exception:
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

        # Batch embed all successful pages at once
        if embed_items:
            try:
                await indexer_service.embed_and_save_batch(embed_items)
            except Exception:
                logger.exception(
                    "%s batch embedding failed for %d items",
                    worker_name,
                    len(embed_items),
                )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting indexer worker")

    migrate()

    indexer.index_job_service.db_path = settings.DB_PATH
    indexer.index_job_service.max_retries = settings.INDEXER_JOB_MAX_RETRIES
    indexer.index_job_service.retry_base_seconds = settings.INDEXER_JOB_RETRY_BASE_SEC
    indexer.index_job_service.retry_max_seconds = settings.INDEXER_JOB_RETRY_MAX_SEC

    pr_task = asyncio.create_task(_pagerank_loop())
    dr_task = asyncio.create_task(_domain_rank_loop())
    cleanup_task = asyncio.create_task(_job_cleanup_loop())
    job_workers = [
        asyncio.create_task(_index_job_worker_loop(f"indexer-worker-{i + 1}"))
        for i in range(max(1, settings.INDEXER_JOB_WORKERS))
    ]

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    await stop_event.wait()

    logger.info("Shutting down indexer worker")
    pr_task.cancel()
    dr_task.cancel()
    cleanup_task.cancel()
    for worker_task in job_workers:
        worker_task.cancel()

    await asyncio.gather(
        pr_task, dr_task, cleanup_task, *job_workers, return_exceptions=True
    )


if __name__ == "__main__":
    asyncio.run(main())
