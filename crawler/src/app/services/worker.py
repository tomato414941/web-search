"""
Worker Service

Manages background crawler worker lifecycle.
"""

import asyncio
import logging
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


class WorkerService:
    """Background crawler worker management"""

    def __init__(self):
        self.task: asyncio.Task | None = None
        self.is_running: bool = False
        self.started_at: datetime | None = None
        self.active_tasks: int = 0
        self.concurrency: int | None = None  # Current concurrency setting

    async def start(self, concurrency: int = 1):
        """Start worker with specified concurrency"""
        if self.is_running:
            raise RuntimeError("Worker is already running")

        # Import here to avoid circular deps
        from app.workers.tasks import worker_loop

        self.concurrency = concurrency
        self.task = asyncio.create_task(worker_loop(concurrency=concurrency))
        self.is_running = True
        self.started_at = datetime.now(UTC)
        logger.info(f"✅ Worker started with concurrency={concurrency}")

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
        self.active_tasks = 0
        self.concurrency = None
        logger.info("✅ Background worker stopped")

    def get_uptime(self) -> float | None:
        """Get worker uptime in seconds"""
        if not self.started_at:
            return None
        return (datetime.now(UTC) - self.started_at).total_seconds()
