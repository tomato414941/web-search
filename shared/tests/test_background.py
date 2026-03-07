import asyncio

import pytest

from shared.core import background


@pytest.mark.asyncio
async def test_maintain_refresh_loop_runs_initial_then_periodic(monkeypatch):
    calls: list[str] = []
    sleep_calls: list[float] = []

    async def initial() -> None:
        calls.append("initial")

    async def periodic() -> None:
        calls.append("periodic")
        raise asyncio.CancelledError

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(background.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await background.maintain_refresh_loop(
            initial_call=initial,
            periodic_call=periodic,
            refresh_interval_seconds=15,
        )

    assert calls == ["initial", "periodic"]
    assert sleep_calls == [15]


@pytest.mark.asyncio
async def test_maintain_refresh_loop_applies_initial_delay(monkeypatch):
    calls: list[str] = []
    sleep_calls: list[float] = []

    async def initial() -> None:
        calls.append("initial")
        raise asyncio.CancelledError

    async def periodic() -> None:
        calls.append("periodic")

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(background.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await background.maintain_refresh_loop(
            initial_call=initial,
            periodic_call=periodic,
            refresh_interval_seconds=15,
            initial_delay_seconds=2,
        )

    assert calls == ["initial"]
    assert sleep_calls == [2]
