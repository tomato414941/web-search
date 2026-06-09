"""Periodic Web model maintenance worker."""

import asyncio
import logging
import os
import signal

from web_search_web_model.rankings import (
    calculate_domain_pagerank,
    calculate_pagerank,
)

logger = logging.getLogger(__name__)


def _interval_hours(name: str, default: int) -> int:
    return max(1, int(os.getenv(name, str(default))))


async def _pagerank_loop() -> None:
    interval = _interval_hours("PAGERANK_INTERVAL_HOURS", 24) * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = await asyncio.to_thread(calculate_pagerank)
            logger.info("Page PageRank recalculated: %s pages", count)
        except Exception:
            logger.exception("Page PageRank calculation failed")


async def _domain_rank_loop() -> None:
    interval = _interval_hours("DOMAIN_RANK_INTERVAL_HOURS", 12) * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            count = await asyncio.to_thread(calculate_domain_pagerank)
            logger.info("Domain PageRank recalculated: %s domains", count)
        except Exception:
            logger.exception("Domain PageRank calculation failed")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting web model maintenance worker")

    tasks = [
        asyncio.create_task(_pagerank_loop(), name="pagerank"),
        asyncio.create_task(_domain_rank_loop(), name="domain-rank"),
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
    for task, result in zip(tasks, results, strict=True):
        if isinstance(result, asyncio.CancelledError):
            continue
        if isinstance(result, Exception):
            logger.exception(
                "Task %s exited with error",
                task.get_name(),
                exc_info=result,
            )


if __name__ == "__main__":
    asyncio.run(main())
