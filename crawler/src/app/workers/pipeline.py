"""
Pipeline stages for URL processing.

Each stage is an independently testable async function.
`process_url` in tasks.py orchestrates these stages.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp

from app.core.blocklist import is_domain_blocked
from app.core.config import settings
from app.db.executor import run_in_db_executor
from app.db.url_store import UrlStore, get_domain
from app.domain.scoring import calculate_url_score, get_domain_rank
from app.scheduler import Scheduler
from app.services.indexer import submit_page_to_indexer
from app.utils import history as history_log
from app.utils.parser import extract_links, html_to_doc_full
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
    priority: float
    blocked_domains: frozenset[str] = field(default_factory=frozenset)
    domain_cache: dict = field(default_factory=dict)


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
    """Run pre-fetch checks (blocklist, URL length, robots, SSRF).

    Returns a skip reason string if the URL should not be fetched,
    or None to proceed. Side-effects: logs and records skips.
    """
    if is_domain_blocked(ctx.domain, ctx.blocked_domains):
        await run_in_db_executor(
            history_log.log_crawl_attempt,
            ctx.url,
            CrawlAttemptStatus.BLOCKED,
            error_message="Domain blocklisted",
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
    """Parse HTML into title, main content, metadata, and extracted outlinks."""
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, html_to_doc_full, html)
    discovered = await loop.run_in_executor(None, extract_links, url, html)
    if discovered:
        discovered = discovered[:max_outlinks]
    return ParseResult(
        title=doc.title,
        content=doc.content,
        outlinks=discovered or [],
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
        ctx.session,
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
    """Score discovered links and enqueue them into the URL store."""
    if not discovered:
        return

    # Batch-fetch domain done counts for uncached domains
    uncached_domains = {
        get_domain(u) for u in discovered if get_domain(u) not in ctx.domain_cache
    }
    if uncached_domains:
        counts = await run_in_db_executor(
            ctx.url_store.domain_done_count_batch, list(uncached_domains)
        )
        for d in uncached_domains:
            ctx.domain_cache[d] = counts.get(d, 0)

    scored_items: list[tuple[str, float]] = []
    for new_url in discovered:
        new_domain = get_domain(new_url)
        if is_domain_blocked(new_domain, ctx.blocked_domains):
            continue
        domain_visits = max(ctx.domain_cache.get(new_domain, 0), 1)
        dr = get_domain_rank(new_domain)
        score = calculate_url_score(
            new_url, ctx.priority, domain_visits, domain_pagerank=dr
        )
        scored_items.append((new_url, score))

    await run_in_db_executor(ctx.url_store.add_batch_scored, scored_items)
    logger.debug("Enqueued links from %s (%d discovered)", ctx.url, len(discovered))
