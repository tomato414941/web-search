"""
Worker Service

Manages background crawler worker lifecycle.
"""

import asyncio
import logging
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


class ActiveTaskCounter:
    """Shared counter for active crawl tasks between WorkerService and worker_loop."""

    def __init__(self):
        self.value: int = 0


class WorkerService:
    """Background crawler worker management"""

    def __init__(self):
        self.task: asyncio.Task | None = None
        self.is_running: bool = False
        self.started_at: datetime | None = None
        self._active_counter = ActiveTaskCounter()
        self.concurrency: int | None = None

    @property
    def active_tasks(self) -> int:
        return self._active_counter.value

    async def start(self, concurrency: int = 1):
        """Start worker with specified concurrency"""
        if self.is_running:
            raise RuntimeError("Worker is already running")

        # Import here to avoid circular deps
        from app.workers.tasks import worker_loop

        self.concurrency = concurrency
        self.task = asyncio.create_task(
            worker_loop(concurrency=concurrency, active_counter=self._active_counter)
        )
        self.is_running = True
        self.started_at = datetime.now(UTC)
        logger.info(f"Worker started with concurrency={concurrency}")

    async def stop(self, graceful: bool = True):
        """Stop background worker"""
        if not self.is_running or not self.task:
            logger.warning("Worker is not running")
            return

        if graceful:
            logger.info("Stopping worker gracefully (waiting for current tasks)...")
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        else:
            logger.info("Stopping worker immediately...")
            self.task.cancel()

        self.is_running = False
        self.started_at = None
        self._active_counter.value = 0
        self.concurrency = None
        logger.info("Background worker stopped")

    def get_uptime(self) -> float | None:
        """Get worker uptime in seconds"""
        if not self.started_at:
            return None
        return (datetime.now(UTC) - self.started_at).total_seconds()
