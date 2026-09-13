import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from web_search_crawler.services import link_observation
from web_search_web_model.archive.outbox import ArchiveFull


@pytest.mark.asyncio
async def test_backpressure_retries_the_same_parsed_observation(monkeypatch):
    graph = Mock()
    graph.replace_observed_links.side_effect = [ArchiveFull(), 1]
    ctx = SimpleNamespace(link_graph=graph, url="https://example.com/")
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(link_observation.asyncio, "sleep", sleep)
    await link_observation.record_links(ctx, ["https://other.example/"])
    assert graph.replace_observed_links.call_count == 2
    assert (
        graph.replace_observed_links.call_args_list[0]
        == graph.replace_observed_links.call_args_list[1]
    )
    assert sleeps == [10]


@pytest.mark.asyncio
async def test_backpressure_wait_can_be_cancelled(monkeypatch):
    graph = Mock()
    graph.replace_observed_links.side_effect = ArchiveFull()
    ctx = SimpleNamespace(link_graph=graph, url="https://example.com/")

    async def sleep(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(link_observation.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await link_observation.record_links(ctx, [])
    assert graph.replace_observed_links.call_count == 1
