"""Unit tests for individual pipeline stages."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from web_search_crawler.services.fetchers import (
    FetchResult,
    _is_feed_content_type,
    _is_html_content_type,
)
from web_search_crawler.workers.pipeline import (
    execute_crawl,
    _non_html_reason,
    process_fetch_result,
    precheck,
)
from web_search_crawler.workers.types import PipelineContext
from web_search_crawler.services.indexer import IndexerSubmitResult


class TestHelpers:
    def test_is_html_content_type_true(self):
        assert _is_html_content_type("text/html; charset=utf-8") is True
        assert _is_html_content_type("application/xhtml+xml") is True

    def test_is_html_content_type_false(self):
        assert _is_html_content_type("application/json") is False
        assert _is_html_content_type("image/png") is False
        assert _is_html_content_type("") is False

    def test_is_feed_content_type_true(self):
        assert _is_feed_content_type("application/rss+xml; charset=utf-8") is True
        assert _is_feed_content_type("text/xml") is True

    def test_is_feed_content_type_false(self):
        assert _is_feed_content_type("text/html") is False
        assert _is_feed_content_type("application/json") is False

    def test_non_html_reason(self):
        assert "application/json" in _non_html_reason("application/json")

    def test_non_html_reason_empty(self):
        assert "unknown" in _non_html_reason("")


def _make_ctx(**overrides) -> PipelineContext:
    defaults = dict(
        session=MagicMock(),
        robots=MagicMock(),
        url_store=MagicMock(),
        planner=MagicMock(),
        url="http://example.com/page",
        blocked_domains=frozenset(),
        domain_cache={},
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


class TestPrecheck:
    @pytest.mark.asyncio
    async def test_blocked_domain_returns_reason(self):
        ctx = _make_ctx(blocked_domains=frozenset({"example.com"}))
        ctx.url_store.record_frontier_result = MagicMock()
        with patch(
            "web_search_crawler.workers.pipeline.run_in_db_executor",
            new_callable=AsyncMock,
        ):
            result = await precheck(ctx)
        assert result == "blocked"

    @pytest.mark.asyncio
    async def test_url_too_long_returns_reason(self):
        ctx = _make_ctx(url="http://example.com/" + "x" * 10000)
        ctx.url_store.record_frontier_result = MagicMock()
        with patch(
            "web_search_crawler.workers.pipeline.run_in_db_executor",
            new_callable=AsyncMock,
        ):
            result = await precheck(ctx)
        assert result == "url_too_long"

    @pytest.mark.asyncio
    async def test_robots_blocked(self):
        ctx = _make_ctx()
        ctx.robots.can_fetch = AsyncMock(return_value=False)
        ctx.url_store.record_frontier_result = MagicMock()
        with patch(
            "web_search_crawler.workers.pipeline.run_in_db_executor",
            new_callable=AsyncMock,
        ):
            result = await precheck(ctx)
        assert result == "robots_blocked"

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        ctx = _make_ctx()
        ctx.robots.can_fetch = AsyncMock(return_value=True)
        ctx.robots.get_crawl_delay = MagicMock(return_value=None)
        ctx.url_store.record_frontier_result = MagicMock()
        with (
            patch(
                "web_search_crawler.workers.pipeline.run_in_db_executor",
                new_callable=AsyncMock,
            ),
            patch(
                "web_search_crawler.workers.pipeline.resolve_is_private_async",
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
            patch(
                "web_search_crawler.workers.pipeline.run_in_db_executor",
                new_callable=AsyncMock,
            ),
            patch(
                "web_search_crawler.workers.pipeline.resolve_is_private_async",
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
            patch(
                "web_search_crawler.workers.pipeline.run_in_db_executor",
                new_callable=AsyncMock,
            ),
            patch(
                "web_search_crawler.workers.pipeline.resolve_is_private_async",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await precheck(ctx)
        assert result is None


class TestProcessFetchResult:
    @pytest.mark.asyncio
    async def test_retryable_http_status_returns_retry_without_side_effects(self):
        ctx = _make_ctx()
        with patch(
            "web_search_crawler.workers.pipeline.run_in_db_executor",
            new_callable=AsyncMock,
        ):
            outcome = await process_fetch_result(
                ctx,
                FetchResult(status=503, content_type="text/html"),
                max_outlinks=50,
                retryable_statuses=(503,),
            )

        assert outcome.status == "retry"
        assert outcome.message == "HTTP 503"
        assert outcome.host_error is True

    @pytest.mark.asyncio
    async def test_non_html_200_is_logged_as_skipped(self):
        ctx = _make_ctx()
        with patch(
            "web_search_crawler.workers.pipeline.run_in_db_executor",
            new_callable=AsyncMock,
        ) as mock_exec:
            outcome = await process_fetch_result(
                ctx,
                FetchResult(status=200, content_type="application/json"),
                max_outlinks=50,
            )

        assert outcome.status == "skipped"
        assert outcome.message == "Non-HTML content-type: application/json"
        assert mock_exec.await_count == 2

    @pytest.mark.asyncio
    async def test_successful_html_returns_index_job_and_outlinks(self):
        ctx = _make_ctx()
        with (
            patch(
                "web_search_crawler.services.html_processing.parse_page",
                return_value=MagicMock(
                    title="Title",
                    content="Body",
                    outlinks=["http://example.com/a", "http://example.com/b"],
                    feed_links=["https://example.com/news/rss.xml"],
                    published_at=None,
                    updated_at=None,
                    author=None,
                    organization=None,
                ),
            ),
            patch(
                "web_search_crawler.services.html_processing.submit_html_page_to_indexer",
                new=AsyncMock(
                    return_value=IndexerSubmitResult(
                        ok=True,
                        status_code=202,
                        job_id="job-123",
                    )
                ),
            ),
            patch(
                "web_search_crawler.services.html_processing.admit_discovered_urls",
                new=AsyncMock(),
            ) as mock_admit,
        ):
            outcome = await process_fetch_result(
                ctx,
                FetchResult(
                    status=200,
                    content_type="text/html",
                    body="<html><body>Body</body></html>",
                ),
                max_outlinks=50,
            )

        assert outcome.status == "queued_for_index"
        assert outcome.message == "Page queued for indexing"
        assert outcome.job_id == "job-123"
        assert outcome.outlinks_discovered == 2
        assert mock_admit.await_count == 2
        mock_admit.assert_any_await(
            ctx,
            ["https://example.com/news/rss.xml"],
            discovery_depth=0,
        )
        mock_admit.assert_any_await(
            ctx,
            ["http://example.com/a", "http://example.com/b"],
        )

    @pytest.mark.asyncio
    async def test_feed_autodiscovery_uses_depth_zero(self):
        ctx = _make_ctx()
        with patch(
            "web_search_crawler.services.url_discovery.run_in_db_executor",
            new_callable=AsyncMock,
        ) as mock_db:
            from web_search_crawler.services.url_discovery import admit_discovered_urls

            await admit_discovered_urls(
                ctx,
                ["https://example.com/news/rss.xml"],
                discovery_depth=0,
            )

        assert mock_db.await_args_list[0].args == (
            ctx.url_store.record_discovered_urls,
            ["https://example.com/news/rss.xml"],
        )
        assert mock_db.await_args_list[1].args == (
            ctx.url_store.admit_urls_to_frontier,
            ["https://example.com/news/rss.xml"],
        )
        assert mock_db.await_args_list[1].kwargs == {
            "admission_intent": "normal",
            "discovery_depth": 0,
        }

    @pytest.mark.asyncio
    async def test_feed_xml_queues_synthetic_entries(self):
        ctx = _make_ctx(url="https://openai.com/news/rss.xml")
        with (
            patch(
                "web_search_crawler.services.feed_processing.parse_feed",
                return_value=[
                    MagicMock(
                        url="https://openai.com/index/our-approach-to-the-model-spec",
                        title="Inside our approach to the Model Spec",
                        content="Learn how OpenAI's Model Spec works.",
                        published_at="2026-03-25T10:00:00+00:00",
                    ),
                    MagicMock(
                        url="https://openai.com/index/safety-bug-bounty",
                        title="Safety bug bounty",
                        content="Program details.",
                        published_at="2026-03-24T10:00:00+00:00",
                    ),
                ],
            ),
            patch(
                "web_search_crawler.services.feed_processing.submit_feed_entry",
                new=AsyncMock(
                    return_value=IndexerSubmitResult(
                        ok=True,
                        status_code=202,
                        job_id="job-feed",
                    )
                ),
            ) as mock_submit,
            patch(
                "web_search_crawler.services.feed_processing.run_in_db_executor",
                new_callable=AsyncMock,
            ) as mock_db,
        ):
            outcome = await process_fetch_result(
                ctx,
                FetchResult(
                    status=200,
                    content_type="application/rss+xml",
                    body="<rss></rss>",
                ),
                max_outlinks=50,
            )

        assert outcome.status == "queued_for_index"
        assert outcome.message == "Feed entries queued for indexing"
        assert outcome.outlinks_discovered == 2
        assert mock_submit.await_count == 2
        mock_db.assert_any_await(
            ctx.url_store.record_discovered_urls,
            [
                "https://openai.com/index/our-approach-to-the-model-spec",
                "https://openai.com/index/safety-bug-bounty",
            ],
        )


class TestExecuteCrawl:
    @pytest.mark.asyncio
    async def test_precheck_skip_short_circuits_before_fetch(self):
        ctx = _make_ctx()
        with (
            patch(
                "web_search_crawler.workers.pipeline.precheck",
                new=AsyncMock(return_value="blocked"),
            ),
            patch(
                "web_search_crawler.workers.pipeline.fetch", new=AsyncMock()
            ) as mock_fetch,
        ):
            outcome = await execute_crawl(ctx, max_outlinks=50)

        assert outcome.status == "skipped"
        assert outcome.message == "Crawl skipped: blocked"
        mock_fetch.assert_not_awaited()
