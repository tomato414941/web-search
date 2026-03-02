"""
Async executor for blocking DB calls.

Provides a dedicated ThreadPoolExecutor so that synchronous
psycopg2 calls do not block the FastAPI / asyncio event loop.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

_DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))
_db_executor = ThreadPoolExecutor(
    max_workers=_DB_POOL_MAX,
    thread_name_prefix="db-io",
)


async def run_in_db_executor(func, *args, **kwargs):
    """Run a sync DB function in the dedicated DB thread pool."""
    loop = asyncio.get_running_loop()
    if kwargs:
        func = partial(func, *args, **kwargs)
        return await loop.run_in_executor(_db_executor, func)
    return await loop.run_in_executor(_db_executor, func, *args)


def shutdown_db_executor():
    """Shutdown the DB executor (call at app shutdown)."""
    _db_executor.shutdown(wait=True)
