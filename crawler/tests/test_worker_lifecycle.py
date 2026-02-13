"""
Worker Lifecycle Tests

Tests for WorkerService and WorkerManager.
"""

import pytest
from unittest.mock import patch, AsyncMock
from app.services.worker import WorkerService
from app.workers.manager import WorkerManager


@pytest.mark.asyncio
async def test_worker_service_start():
    """Test WorkerService.start() creates background task"""
    service = WorkerService()

    with patch("app.workers.tasks.worker_loop", new_callable=AsyncMock):
        await service.start(concurrency=2)

        assert service.is_running is True
        assert service.started_at is not None
        assert service.concurrency == 2
        assert service.task is not None

        # Cleanup
        await service.stop(graceful=False)


@pytest.mark.asyncio
async def test_worker_service_stop_graceful():
    """Test WorkerService.stop(graceful=True) cancels task cleanly"""
    service = WorkerService()

    with patch("app.workers.tasks.worker_loop", new_callable=AsyncMock):
        await service.start(concurrency=1)
        assert service.is_running is True

        await service.stop(graceful=True)

        assert service.is_running is False
        assert service.started_at is None
        assert service.active_tasks == 0
        assert service.concurrency is None


@pytest.mark.asyncio
async def test_worker_service_stop_forceful():
    """Test WorkerService.stop(graceful=False) stops immediately"""
    service = WorkerService()

    with patch("app.workers.tasks.worker_loop", new_callable=AsyncMock):
        await service.start(concurrency=1)

        await service.stop(graceful=False)

        assert service.is_running is False
        assert service.concurrency is None


@pytest.mark.asyncio
async def test_worker_service_start_already_running():
    """Test WorkerService.start() raises error if already running"""
    service = WorkerService()

    with patch("app.workers.tasks.worker_loop", new_callable=AsyncMock):
        await service.start(concurrency=1)

        with pytest.raises(RuntimeError, match="already running"):
            await service.start(concurrency=1)

        # Cleanup
        await service.stop(graceful=False)


def test_worker_service_get_uptime():
    """Test WorkerService.get_uptime() calculates runtime"""
    service = WorkerService()

    # Not started
    assert service.get_uptime() is None

    # Started (mock datetime)
    from datetime import datetime, UTC

    service.started_at = datetime.now(UTC)
    uptime = service.get_uptime()

    assert uptime is not None
    assert uptime >= 0.0


def test_worker_manager_singleton():
    """Test WorkerManager is a singleton"""
    manager1 = WorkerManager()
    manager2 = WorkerManager()

    assert manager1 is manager2
    assert manager1.worker is manager2.worker


@pytest.mark.asyncio
async def test_worker_manager_start_stop():
    """Test WorkerManager start/stop delegates to WorkerService"""
    manager = WorkerManager()

    # Ensure stopped initially
    if manager.is_running:
        await manager.stop(graceful=False)

    with patch("app.workers.tasks.worker_loop", new_callable=AsyncMock):
        # Start
        await manager.start(concurrency=3)
        assert manager.is_running is True

        # Stop
        await manager.stop(graceful=True)
        assert manager.is_running is False


@pytest.mark.asyncio
async def test_worker_manager_get_status_stopped():
    """Test WorkerManager.get_status() when stopped"""
    manager = WorkerManager()

    # Ensure stopped
    if manager.is_running:
        await manager.stop(graceful=False)

    status = await manager.get_status()

    assert status.status == "stopped"
    assert status.active_tasks == 0
    assert status.started_at is None
    assert status.uptime_seconds is None
    assert status.concurrency is None


@pytest.mark.asyncio
async def test_worker_manager_get_status_running():
    """Test WorkerManager.get_status() when running"""
    manager = WorkerManager()

    # Ensure stopped initially
    if manager.is_running:
        await manager.stop(graceful=False)

    with patch("app.workers.tasks.worker_loop", new_callable=AsyncMock):
        await manager.start(concurrency=1)

        status = await manager.get_status()

        assert status.status == "running"
        assert status.started_at is not None
        assert status.uptime_seconds is not None
        assert status.uptime_seconds >= 0.0
        assert status.concurrency == 1

        # Cleanup
        await manager.stop(graceful=False)
