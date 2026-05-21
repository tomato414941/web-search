import asyncio
from collections.abc import Awaitable, Callable


async def maintain_refresh_loop(
    *,
    initial_call: Callable[[], Awaitable[None]],
    periodic_call: Callable[[], Awaitable[None]],
    refresh_interval_seconds: float,
    initial_delay_seconds: float = 0.0,
) -> None:
    refresh_interval_seconds = max(1.0, refresh_interval_seconds)
    initial_delay_seconds = max(0.0, initial_delay_seconds)

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    await initial_call()
    while True:
        await asyncio.sleep(refresh_interval_seconds)
        await periodic_call()
