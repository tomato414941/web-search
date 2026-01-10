"""
Worker Manager

Singleton instance managing the background worker.
"""

from app.services.worker import WorkerService
from app.models.worker import WorkerStatus


class WorkerManager:
    """Singleton worker manager"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.worker = WorkerService()
        return cls._instance

    async def initialize(self):
        """Initialize worker manager (called during app startup)"""
        # Nothing to do here - worker is created but not started
        pass

    async def start(self, concurrency: int = 1):
        """Start background worker with specified concurrency"""
        await self.worker.start(concurrency=concurrency)

    async def stop(self, graceful: bool = True):
        """Stop background worker"""
        await self.worker.stop(graceful=graceful)

    @property
    def is_running(self) -> bool:
        """Check if worker is running"""
        return self.worker.is_running

    async def get_status(self) -> WorkerStatus:
        """Get current worker status"""
        return WorkerStatus(
            status="running" if self.worker.is_running else "stopped",
            active_tasks=self.worker.active_tasks,
            started_at=self.worker.started_at,
            uptime_seconds=self.worker.get_uptime(),
        )


# Singleton instance
worker_manager = WorkerManager()
