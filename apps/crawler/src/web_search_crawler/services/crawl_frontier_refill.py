"""Refill crawl frontier from the observed link graph."""

from dataclasses import dataclass
import math

from web_search_crawler.db.crawler_runtime_store import CrawlerRuntimeStore
from web_search_postgres.search import get_connection
from web_search_web_model import UrlLedgerRepository


@dataclass(frozen=True)
class CrawlFrontierRefillResult:
    candidates: int
    recorded: int
    enqueued: int
    urls: list[str]


def _validate_refill_args(
    *,
    limit: int,
    sample_percent: float,
    sample_limit: int,
    statement_timeout_ms: int,
) -> None:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not math.isfinite(sample_percent) or sample_percent <= 0 or sample_percent > 100:
        raise ValueError("sample_percent must be > 0 and <= 100")
    if sample_limit <= 0:
        raise ValueError("sample_limit must be positive")
    if statement_timeout_ms <= 0:
        raise ValueError("statement_timeout_ms must be positive")


def fetch_link_frontier_candidates(
    *,
    limit: int,
    sample_percent: float = 0.01,
    sample_limit: int = 10_000,
    statement_timeout_ms: int = 30_000,
) -> list[str]:
    """Return diverse unindexed URLs sampled from observed links."""
    _validate_refill_args(
        limit=limit,
        sample_percent=sample_percent,
        sample_limit=sample_limit,
        statement_timeout_ms=statement_timeout_ms,
    )
    con = get_connection()
    try:
        cur = con.cursor()
        try:
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
            cur.execute(
                f"""
                WITH sampled AS MATERIALIZED (
                    SELECT dst
                    FROM links TABLESAMPLE SYSTEM ({sample_percent})
                    WHERE dst IS NOT NULL
                    LIMIT %s
                ), parsed AS MATERIALIZED (
                    SELECT
                        dst,
                        lower(
                            split_part(
                                regexp_replace(
                                    substring(
                                        dst FROM '^[a-z][a-z0-9+.-]*://([^/?#]+)'
                                    ),
                                    '^[^@]*@',
                                    ''
                                ),
                                ':',
                                1
                            )
                        ) AS host
                    FROM sampled
                ), per_host AS (
                    SELECT DISTINCT ON (host)
                        dst,
                        host
                    FROM parsed
                    WHERE host IS NOT NULL AND host <> ''
                    ORDER BY host, random()
                )
                SELECT dst
                FROM per_host AS candidate
                WHERE NOT EXISTS (
                    SELECT 1 FROM documents AS document
                    WHERE document.url = candidate.dst
                )
                  AND NOT EXISTS (
                    SELECT 1 FROM crawl_queue AS queued
                    WHERE queued.url = candidate.dst
                )
                ORDER BY random()
                LIMIT %s
                """,
                (sample_limit, limit),
            )
            return [str(url) for (url,) in cur.fetchall()]
        finally:
            cur.close()
    finally:
        con.close()


def refill_crawl_frontier_from_links(
    *,
    store: CrawlerRuntimeStore,
    url_ledger: UrlLedgerRepository,
    limit: int,
    sample_percent: float = 0.01,
    sample_limit: int = 10_000,
    statement_timeout_ms: int = 30_000,
    dry_run: bool = False,
) -> CrawlFrontierRefillResult:
    """Sample observed links and enqueue diverse unindexed URLs."""
    urls = fetch_link_frontier_candidates(
        limit=limit,
        sample_percent=sample_percent,
        sample_limit=sample_limit,
        statement_timeout_ms=statement_timeout_ms,
    )
    if dry_run:
        return CrawlFrontierRefillResult(
            candidates=len(urls),
            recorded=0,
            enqueued=0,
            urls=urls,
        )

    recorded = url_ledger.record_discovered_urls(urls)
    enqueued = store.enqueue_urls_for_crawl(urls)
    return CrawlFrontierRefillResult(
        candidates=len(urls),
        recorded=recorded,
        enqueued=enqueued,
        urls=urls,
    )
