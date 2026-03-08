"""Unit tests for individual pipeline stages."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.pipeline import (
    PipelineContext,
    _is_html_content_type,
    _non_html_reason,
    precheck,
)


class TestHelpers:
    def test_is_html_content_type_true(self):
        assert _is_html_content_type("text/html; charset=utf-8") is True
        assert _is_html_content_type("application/xhtml+xml") is True

    def test_is_html_content_type_false(self):
        assert _is_html_content_type("application/json") is False
        assert _is_html_content_type("image/png") is False
        assert _is_html_content_type("") is False

    def test_non_html_reason(self):
        assert "application/json" in _non_html_reason("application/json")

    def test_non_html_reason_empty(self):
        assert "unknown" in _non_html_reason("")


def _make_ctx(**overrides) -> PipelineContext:
    defaults = dict(
        session=MagicMock(),
        robots=MagicMock(),
        url_store=MagicMock(),
        scheduler=MagicMock(),
        url="http://example.com/page",
        domain="example.com",
        blocked_domains=frozenset(),
        domain_cache={},
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


class TestPrecheck:
    @pytest.mark.asyncio
    async def test_blocked_domain_returns_reason(self):
        ctx = _make_ctx(blocked_domains=frozenset({"example.com"}))
        ctx.url_store.record = MagicMock()
        with patch("app.workers.pipeline.run_in_db_executor", new_callable=AsyncMock):
            result = await precheck(ctx)
        assert result == "blocked"

    @pytest.mark.asyncio
    async def test_url_too_long_returns_reason(self):
        ctx = _make_ctx(url="http://example.com/" + "x" * 10000)
        ctx.url_store.record = MagicMock()
        with patch("app.workers.pipeline.run_in_db_executor", new_callable=AsyncMock):
            result = await precheck(ctx)
        assert result == "url_too_long"

    @pytest.mark.asyncio
    async def test_robots_blocked(self):
        ctx = _make_ctx()
        ctx.robots.can_fetch = AsyncMock(return_value=False)
        ctx.url_store.record = MagicMock()
        with patch("app.workers.pipeline.run_in_db_executor", new_callable=AsyncMock):
            result = await precheck(ctx)
        assert result == "robots_blocked"

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        ctx = _make_ctx()
        ctx.robots.can_fetch = AsyncMock(return_value=True)
        ctx.robots.get_crawl_delay = MagicMock(return_value=None)
        ctx.url_store.record = MagicMock()
        with (
            patch("app.workers.pipeline.run_in_db_executor", new_callable=AsyncMock),
            patch(
                "app.workers.pipeline.resolve_is_private_async",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await precheck(ctx)
        assert result == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_passes_all_checks(self):
        ctx = _make_ctx()
        ctx.robots.can_fetch = AsyncMock(return_value=True)
        ctx.robots.get_crawl_delay = MagicMock(return_value=None)
        with (
            patch("app.workers.pipeline.run_in_db_executor", new_callable=AsyncMock),
            patch(
                "app.workers.pipeline.resolve_is_private_async",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await precheck(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_crawl_delay_applied(self):
        ctx = _make_ctx()
        ctx.robots.can_fetch = AsyncMock(return_value=True)
        ctx.robots.get_crawl_delay = MagicMock(return_value=5.0)
        with (
            patch("app.workers.pipeline.run_in_db_executor", new_callable=AsyncMock),
            patch(
                "app.workers.pipeline.resolve_is_private_async",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await precheck(ctx)
        assert result is None
        ctx.scheduler.set_crawl_delay.assert_called_once_with("example.com", 5.0)
