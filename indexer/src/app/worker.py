import asyncio
import logging
import os
import signal

from app.api.routes import indexer
from app.core.config import settings
from app.services.indexer import indexer_service
from shared.db.search import ensure_db
from shared.pagerank import calculate_domain_pagerank, calculate_pagerank

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


async def _domain_rank_loop() -> None:
    interval = settings.DOMAIN_RANK_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = calculate_domain_pagerank(settings.DB_PATH)
            logger.info("Domain PageRank recalculated: %s domains", count)
        except Exception:
            logger.exception("Domain PageRank calculation failed")


async def _index_job_worker_loop(worker_name: str) -> None:
    poll_interval = max(settings.INDEXER_JOB_POLL_INTERVAL_MS, 50) / 1000.0

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

        for job in jobs:
            try:
                await indexer_service.index_page(
                    url=job.url,
                    title=job.title,
                    content=job.content,
                    outlinks=job.outlinks,
                )
                indexer.index_job_service.mark_done(job.job_id)
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


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting indexer worker")

    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    ensure_db(settings.DB_PATH)

    indexer.index_job_service.db_path = settings.DB_PATH
    indexer.index_job_service.max_retries = settings.INDEXER_JOB_MAX_RETRIES
    indexer.index_job_service.retry_base_seconds = settings.INDEXER_JOB_RETRY_BASE_SEC
    indexer.index_job_service.retry_max_seconds = settings.INDEXER_JOB_RETRY_MAX_SEC

    pr_task = asyncio.create_task(_pagerank_loop())
    dr_task = asyncio.create_task(_domain_rank_loop())
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
    for worker_task in job_workers:
        worker_task.cancel()

    await asyncio.gather(pr_task, dr_task, *job_workers, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
