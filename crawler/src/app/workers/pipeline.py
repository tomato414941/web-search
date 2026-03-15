"""
Pipeline stages for URL processing.

Each stage is an independently testable async function.
`process_url` in tasks.py orchestrates these stages.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp

from app.core.crawl_denylist import is_domain_denied
from app.core.config import settings
from app.core.url_filters import UrlFilter
from app.db.executor import run_in_db_executor
from app.db.url_store import UrlStore
from app.db.url_types import get_domain
from app.scheduler import Scheduler
from app.services.indexer import submit_page_to_indexer
from app.utils import history as history_log
from app.utils.parser import parse_page
from app.utils.robots import AsyncRobotsCache
from shared.contracts.enums import CrawlAttemptStatus, CrawlUrlStatus
from shared.core.utils import MAX_URL_LENGTH, resolve_is_private_async

logger = logging.getLogger(__name__)

# Maximum response size (10 MB)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024


@dataclass
class PipelineContext:
    """Shared state passed through pipeline stages."""

    session: aiohttp.ClientSession
    robots: AsyncRobotsCache
    url_store: UrlStore
    scheduler: Scheduler
    url: str
    domain: str
    blocked_domains: frozenset[str] = field(default_factory=frozenset)
    url_filter: UrlFilter | None = None
    domain_cache: dict = field(default_factory=dict)
    indexer_session: aiohttp.ClientSession | None = None


@dataclass
class FetchResult:
    """Result of an HTTP fetch."""

    status: int
    content_type: str
    body: str | None = None
    error: str | None = None


@dataclass
class ParseResult:
    """Result of HTML parsing."""

    title: str
    content: str
    outlinks: list[str]
    published_at: str | None = None
    updated_at: str | None = None
    author: str | None = None
    organization: str | None = None


def _is_html_content_type(content_type: str) -> bool:
    return "text/html" in content_type or "application/xhtml" in content_type


def _non_html_reason(content_type: str) -> str:
    normalized = content_type.strip() or "unknown"
    return f"Non-HTML content-type: {normalized}"


async def precheck(ctx: PipelineContext) -> str | None:
    """Run pre-fetch checks (denylist, URL length, robots, SSRF).

    Returns a skip reason string if the URL should not be fetched,
    or None to proceed. Side-effects: logs and records skips.
    """
    if is_domain_denied(ctx.domain, ctx.blocked_domains):
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="Domain denied by crawl denylist",
        )
        await run_in_db_executor(ctx.url_store.record, ctx.url, CrawlUrlStatus.FAILED)
        return "blocked"

    if len(ctx.url) > MAX_URL_LENGTH:
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.SKIPPED,
            error_message=f"URL too long: {len(ctx.url)} > {MAX_URL_LENGTH}",
        )
        await run_in_db_executor(ctx.url_store.record, ctx.url, CrawlUrlStatus.FAILED)
        return "url_too_long"

    if not await ctx.robots.can_fetch(ctx.url, settings.CRAWL_USER_AGENT):
        logger.info("Blocked by robots.txt: %s", ctx.url)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="Blocked by robots.txt",
        )
        await run_in_db_executor(ctx.url_store.record, ctx.url, CrawlUrlStatus.FAILED)
        return "robots_blocked"

    if await resolve_is_private_async(ctx.domain):
        logger.warning("SSRF blocked: %s resolves to private IP", ctx.url)
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="SSRF: private IP",
        )
        await run_in_db_executor(ctx.url_store.record, ctx.url, CrawlUrlStatus.FAILED)
        return "ssrf_blocked"

    # Apply crawl-delay from robots.txt
    crawl_delay = ctx.robots.get_crawl_delay(ctx.domain, settings.CRAWL_USER_AGENT)
    if crawl_delay is not None:
        ctx.scheduler.set_crawl_delay(ctx.domain, crawl_delay)

    return None


async def fetch(ctx: PipelineContext) -> FetchResult:
    """Perform the HTTP fetch and return the result.

    Does NOT log/record — the caller handles response-level decisions.
    """
    async with ctx.session.get(
        ctx.url, timeout=settings.CRAWL_TIMEOUT_SEC, allow_redirects=True
    ) as resp:
        ct = resp.headers.get("Content-Type", "").lower()

        content_length = resp.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > MAX_RESPONSE_SIZE:
                    return FetchResult(
                        status=resp.status,
                        content_type=ct,
                        error=f"Response too large: {content_length} bytes",
                    )
            except ValueError:
                pass

        if resp.status != 200 or not _is_html_content_type(ct):
            return FetchResult(status=resp.status, content_type=ct)

        body = await resp.content.read(MAX_RESPONSE_SIZE)
        if len(body) >= MAX_RESPONSE_SIZE:
            return FetchResult(
                status=resp.status,
                content_type=ct,
                error=f"Response truncated at {MAX_RESPONSE_SIZE} bytes",
            )

        html = body.decode("utf-8", errors="replace")
        return FetchResult(status=resp.status, content_type=ct, body=html)


async def parse(html: str, url: str, max_outlinks: int) -> ParseResult:
    """Parse HTML into title, main content, metadata, and extracted outlinks.

    Uses parse_page() which parses HTML once (lxml) for both content and links.
    """
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, parse_page, html, url, max_outlinks)
    return ParseResult(
        title=doc.title,
        content=doc.content,
        outlinks=doc.outlinks or [],
        published_at=doc.published_at,
        updated_at=doc.updated_at,
        author=doc.author,
        organization=doc.organization,
    )


async def submit_to_indexer(ctx: PipelineContext, parsed: ParseResult) -> bool:
    """Submit parsed page to the indexer API.

    Returns True on success. Logs and records the result.
    """
    result = await submit_page_to_indexer(
        ctx.indexer_session or ctx.session,
        settings.INDEXER_API_URL,
        settings.INDEXER_API_KEY,
        ctx.url,
        parsed.title,
        parsed.content,
        outlinks=parsed.outlinks,
        published_at=parsed.published_at,
        updated_at=parsed.updated_at,
        author=parsed.author,
        organization=parsed.organization,
    )

    if result.ok:
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.QUEUED_FOR_INDEX,
            result.status_code or 202,
            f"job_id={result.job_id}" if result.job_id else None,
        )
        await run_in_db_executor(ctx.url_store.record, ctx.url, CrawlUrlStatus.DONE)
        return True

    http_code = result.status_code or 500
    error_message = result.detail or f"Indexer API rejected ({http_code})"
    await run_in_db_executor(
        history_log.log_crawl_attempt,
        ctx.url,
        CrawlAttemptStatus.INDEXER_ERROR,
        http_code,
        error_message,
    )
    await run_in_db_executor(ctx.url_store.record, ctx.url, CrawlUrlStatus.FAILED)
    return False


async def discover_and_enqueue_links(
    ctx: PipelineContext, discovered: list[str]
) -> None:
    """Filter and enqueue discovered links into the crawl queue."""
    if not discovered:
        return

    # Filter: length + denylist + URL patterns
    valid_urls = [
        u
        for u in discovered
        if len(u) <= MAX_URL_LENGTH
        and not is_domain_denied(get_domain(u), ctx.blocked_domains)
        and not (ctx.url_filter and ctx.url_filter.is_filtered(u))
    ]

    if valid_urls:
        await run_in_db_executor(ctx.url_store.add_batch, valid_urls)
    logger.debug("Enqueued links from %s (%d discovered)", ctx.url, len(discovered))
