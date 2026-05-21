import asyncio
import fcntl
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator


def snapshot_timestamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _acquire_file_lock(
    lock_path: str, *, label: str, logger: logging.Logger
) -> Any | None:
    lock_dir = os.path.dirname(lock_path)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)

    try:
        handle = open(lock_path, "a+", encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to open %s build lock: %s", label, exc)
        return None

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError as exc:
        logger.warning("Failed to acquire %s build lock: %s", label, exc)
        handle.close()
        return None

    return handle


def _release_file_lock(
    handle: Any | None, *, label: str, logger: logging.Logger
) -> None:
    if handle is None:
        return

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        logger.warning("Failed to release %s build lock: %s", label, exc)
    finally:
        handle.close()


@asynccontextmanager
async def build_singleflight(
    memory_lock: asyncio.Lock,
    *,
    cache_path: str,
    label: str,
    logger: logging.Logger,
) -> AsyncIterator[None]:
    async with memory_lock:
        lock_path = f"{cache_path}.lock"
        handle = await asyncio.to_thread(
            _acquire_file_lock,
            lock_path,
            label=label,
            logger=logger,
        )
        try:
            yield
        finally:
            await asyncio.to_thread(
                _release_file_lock,
                handle,
                label=label,
                logger=logger,
            )
