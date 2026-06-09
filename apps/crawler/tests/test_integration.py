"""
Integration Tests

End-to-end tests for the full crawler workflow.
"""

import time

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from psycopg2.errors import DeadlockDetected

from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db import CrawlerRuntimeStore
from web_search_crawler.crawl_task_planner import (
    CrawlTaskPlanner,
    CrawlTaskPlannerConfig,
)
from web_search_crawler.services.crawl_scheduling import (
    compute_failure_retry_delay_for_url,
)
from web_search_crawler.services.indexer import IndexerSubmitResult
from web_search_crawler.utils.parser import ParsedDocument
from web_search_crawler.workers.tasks import process_url
from web_search_core.urls import url_hash
from web_search_web_knowledge import LinkGraphRepository, UrlLedgerRepository


@pytest.fixture
def test_components(tmp_path):
    """Create test CrawlerRuntimeStore and frontier planner."""
    db_path = str(tmp_path / "test.db")
    url_store = CrawlerRuntimeStore(db_path, recrawl_after_days=30)
    url_ledger = UrlLedgerRepository(url_store.url_admission_policy)
    link_graph = LinkGraphRepository(url_store.url_admission_policy)
    planner = CrawlTaskPlanner(url_store, CrawlTaskPlannerConfig())
    return url_store, url_ledger, link_graph, planner


def _url_ledger_contains(url_store: CrawlerRuntimeStore, url: str) -> bool:
    with db_transaction(url_store.db_path) as cur:
        cur.execute("SELECT 1 FROM urls WHERE url_hash = %s", (url_hash(url),))
        return cur.fetchone() is not None


def _url_ledger_repository(url_store: CrawlerRuntimeStore) -> UrlLedgerRepository:
    return UrlLedgerRepository(url_store.url_admission_policy)


def _record_and_admit_url(
    url_store: CrawlerRuntimeStore,
    url: str,
    *,
    admission_intent: str = "normal",
) -> bool:
    _url_ledger_repository(url_store).record_discovered_url(url)
    return url_store.schedule_url_for_crawl(
        url,
        admission_intent=admission_intent,
    )


def _record_and_admit_urls(
    url_store: CrawlerRuntimeStore,
    urls: list[str],
    *,
    admission_intent: str = "normal",
) -> int:
    _url_ledger_repository(url_store).record_discovered_urls(urls)
    return url_store.schedule_urls_for_crawl(
        urls,
        admission_intent=admission_intent,
    )


@pytest.mark.asyncio
async def test_process_url_success_flow(test_components):
    """Test complete process_url flow with successful indexing"""
    url_store, url_ledger, link_graph, planner = test_components

    # Mock dependencies
    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <p>Test content</p>
            <a href="/link1">Link 1</a>
        </body>
        </html>
    """
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch(
        "web_search_crawler.services.html_processing.parse_page",
        return_value=ParsedDocument(
            title="Test Page",
            content="Test content",
            outlinks=["http://example.com/link1"],
        ),
    ):
        with patch(
            "web_search_crawler.services.html_processing.submit_page_to_indexer",
            new_callable=AsyncMock,
        ) as mock_indexer:
            with patch(
                "web_search_crawler.workers.tasks.history_log.log_crawl_attempt"
            ):
                mock_indexer.return_value = IndexerSubmitResult(
                    ok=True, status_code=202, job_id="job-1"
                )

                await process_url(
                    mock_session,
                    mock_robots,
                    url_store,
                    url_ledger,
                    link_graph,
                    planner,
                    "http://example.com/test",
                )

                # Verify robots check
                mock_robots.can_fetch.assert_called_once()

                # Verify HTTP fetch
                mock_session.get.assert_called_once()

                # Verify indexer submission
                mock_indexer.assert_called_once()

                # Verify URL was recorded
                assert _url_ledger_contains(url_store, "http://example.com/test")


@pytest.mark.asyncio
async def test_process_url_robots_blocked(test_components):
    """Test process_url when robots.txt blocks URL"""
    url_store, url_ledger, link_graph, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = False  # Blocked
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    with patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            "http://example.com/blocked",
        )

        # Should not fetch
        mock_session.get.assert_not_called()

        # URL should be recorded as failed
        assert _url_ledger_contains(url_store, "http://example.com/blocked")


@pytest.mark.asyncio
async def test_process_url_http_error(test_components):
    """Test process_url with HTTP error (404)"""
    url_store, url_ledger, link_graph, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock 404 response
    mock_response = AsyncMock()
    mock_response.status = 404
    mock_response.headers = {"Content-Type": "text/html"}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            "http://example.com/notfound",
        )

        # URL should be recorded as failed
        assert _url_ledger_contains(url_store, "http://example.com/notfound")


@pytest.mark.asyncio
async def test_process_url_network_error(test_components):
    """Test process_url with network error returning the URL to the frontier."""
    url_store, url_ledger, link_graph, planner = test_components
    test_url = "http://example.com/error"

    # Add URL to frontier then lease it (simulates real flow)
    _record_and_admit_url(url_store, test_url)
    url_store.lease_ready_crawl_tasks(1)

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock network error
    import aiohttp

    mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

    with patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            test_url,
        )

        # URL should be returned to pending frontier state for retry
        entry = url_store.get_crawl_schedule_entry(test_url)
        assert entry is not None
        assert entry.status == "pending"


@pytest.mark.asyncio
async def test_process_url_discovers_links(test_components):
    """Test that process_url adds discovered links to url_store"""
    url_store, url_ledger, link_graph, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"<html><body>Test</body></html>"
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch(
        "web_search_crawler.services.html_processing.parse_page",
        return_value=ParsedDocument(
            title="Test",
            content="Content",
            published_at=None,
            updated_at=None,
            author=None,
            organization=None,
            outlinks=[
                "http://example.com/link1",
                "http://example.com/link2",
            ],
        ),
    ):
        with patch(
            "web_search_crawler.services.html_processing.submit_page_to_indexer",
            new_callable=AsyncMock,
        ) as mock_indexer:
            with patch(
                "web_search_crawler.workers.tasks.history_log.log_crawl_attempt"
            ):
                mock_indexer.return_value = IndexerSubmitResult(
                    ok=True, status_code=202, job_id="job-2"
                )

                await process_url(
                    mock_session,
                    mock_robots,
                    url_store,
                    url_ledger,
                    link_graph,
                    planner,
                    "http://example.com/",
                )

                # Discovered links should be in url_store
                assert _url_ledger_contains(url_store, "http://example.com/link1")
                assert _url_ledger_contains(url_store, "http://example.com/link2")


def test_record_and_admit_populates_frontier_entry_for_outlinks(test_url_store):
    added = _record_and_admit_urls(test_url_store, ["http://example.com/1"])

    entry = test_url_store.get_crawl_schedule_entry("http://example.com/1")
    domain_state = test_url_store.get_domain_state("example.com")

    assert added == 1
    assert entry is not None
    assert entry.status == "pending"
    assert domain_state is not None


def test_record_discovered_urls_writes_ledger_without_frontier(test_url_store):
    recorded = _url_ledger_repository(test_url_store).record_discovered_urls(
        ["https://example.com/article-entry"]
    )

    assert recorded == 1
    assert _url_ledger_contains(test_url_store, "https://example.com/article-entry")
    assert (
        test_url_store.get_crawl_schedule_entry("https://example.com/article-entry")
        is None
    )


def test_lease_ready_crawl_tasks_retries_after_deadlock(test_url_store, monkeypatch):
    _record_and_admit_urls(test_url_store, ["http://example.com/frontier"])

    original = test_url_store._lease_crawl_candidates
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise DeadlockDetected("deadlock detected")
        return original(*args, **kwargs)

    monkeypatch.setattr(test_url_store, "_lease_crawl_candidates", flaky)

    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    assert [item.url for item in leased] == ["http://example.com/frontier"]
    assert calls["count"] >= 2


def test_lease_ready_crawl_tasks_leases_url_and_clears_pending_frontier_state(
    test_url_store,
):
    _record_and_admit_urls(test_url_store, ["http://example.com/frontier"])

    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)
    entry = test_url_store.get_crawl_schedule_entry("http://example.com/frontier")
    domain_state = test_url_store.get_domain_state("example.com")

    assert [item.url for item in leased] == ["http://example.com/frontier"]
    assert entry is not None
    assert entry.status == "leased"
    assert domain_state is not None
    assert domain_state.inflight_leases == 1


def test_lease_ready_crawl_tasks_prefers_priority_bucket(test_url_store):
    urls = [
        "https://docs.python.org/3/whatsnew/3.13.html",
        "https://kubernetes.io/docs/",
        "https://example.com/a-generic-page",
    ]
    _record_and_admit_urls(test_url_store, urls)

    leased = test_url_store.lease_ready_crawl_tasks(2, lease_seconds=120)

    assert {item.url for item in leased} == {
        "https://docs.python.org/3/whatsnew/3.13.html",
        "https://kubernetes.io/docs/",
    }


def test_lease_ready_crawl_tasks_leases_generic_urls(test_url_store):
    urls = [
        "https://example.com/a-generic-page",
        "https://example.org/another-generic-page",
    ]
    _record_and_admit_urls(test_url_store, urls)

    leased = test_url_store.lease_ready_crawl_tasks(2, lease_seconds=120)

    assert {item.url for item in leased} == set(urls)


def test_lease_ready_crawl_tasks_does_not_duplicate_leases(test_url_store):
    urls = [
        "https://example.com/only-generic",
        "https://example.org/also-generic",
    ]
    _record_and_admit_urls(test_url_store, urls)

    leased = test_url_store.lease_ready_crawl_tasks(4, lease_seconds=120)
    leased_urls = [item.url for item in leased]

    assert sorted(leased_urls) == sorted(urls)
    assert len(leased_urls) == len(set(leased_urls))
    assert all(
        test_url_store.get_crawl_schedule_entry(url).status == "leased" for url in urls
    )


def test_lease_ready_crawl_tasks_skips_domains_blocked_by_domain_state(test_url_store):
    blocked = "https://blocked.example.com/page"
    ready = "https://ready.example.com/page"
    _record_and_admit_urls(test_url_store, [blocked, ready])
    test_url_store.set_domain_crawl_delay("blocked.example.com", 1.0)

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE domain_state
            SET next_request_at = %s
            WHERE domain = %s
            """,
            (int(time.time()) + 300, "blocked.example.com"),
        )

    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    assert [item.url for item in leased] == [ready]


def test_record_updates_frontier_after_success(test_url_store):
    _record_and_admit_urls(
        test_url_store, ["https://docs.docker.com/reference/cli/docker/"]
    )
    test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_task_result(
        "https://docs.docker.com/reference/cli/docker/",
        "done",
    )
    after = int(time.time())
    entry = test_url_store.get_crawl_schedule_entry(
        "https://docs.docker.com/reference/cli/docker/"
    )
    domain_state = test_url_store.get_domain_state("docs.docker.com")

    assert entry is not None
    assert entry.status == "pending"
    assert entry.next_fetch_at >= before + 7 * 24 * 3600
    assert entry.next_fetch_at <= after + 7 * 24 * 3600 + 1
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert domain_state.fail_streak == 0
    assert domain_state.next_request_at >= before


def test_recent_fetch_suppression_uses_frontier_state(test_url_store):
    url = "https://example.com/recent"
    _record_and_admit_urls(test_url_store, [url])
    test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)
    test_url_store.record_crawl_task_result(url, "done")
    before_entry = test_url_store.get_crawl_schedule_entry(url)

    added = _record_and_admit_urls(test_url_store, [url])
    after_entry = test_url_store.get_crawl_schedule_entry(url)

    assert added == 0
    assert before_entry is not None
    assert after_entry is not None
    assert after_entry.next_fetch_at == before_entry.next_fetch_at


def test_record_failure_updates_frontier_and_domain_state(test_url_store):
    url = "https://example.com/failure"
    _record_and_admit_urls(test_url_store, [url])
    test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_task_result(url, "failed")
    after = int(time.time())
    entry = test_url_store.get_crawl_schedule_entry(url)
    domain_state = test_url_store.get_domain_state("example.com")

    assert entry is not None
    assert entry.status == "pending"
    retry_delay = compute_failure_retry_delay_for_url(url, fail_streak=0)
    assert entry.next_fetch_at >= before + retry_delay
    assert entry.next_fetch_at <= after + retry_delay + 1
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert domain_state.fail_streak == 1
    assert domain_state.backoff_until is not None
    assert domain_state.backoff_until >= before


def test_operator_priority_admission_applies_one_time_priority_override(test_url_store):
    url = "https://docs.docker.com/reference/cli/docker/"
    _record_and_admit_urls(test_url_store, [url], admission_intent="operator_priority")
    entry = test_url_store.get_crawl_schedule_entry(url)

    assert entry is not None
    assert entry.priority_bucket == 0

    test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_task_result(url, "done")
    after = int(time.time())
    entry = test_url_store.get_crawl_schedule_entry(url)

    assert entry is not None
    assert entry.status == "pending"
    assert entry.priority_bucket == 1
    assert entry.next_fetch_at >= before + 7 * 24 * 3600
    assert entry.next_fetch_at <= after + 7 * 24 * 3600 + 1


def test_release_notes_failure_retries_quickly(test_url_store):
    url = "https://docs.python.org/3/whatsnew/3.13.html"
    _record_and_admit_urls(test_url_store, [url])
    test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_task_result(url, "failed")
    after = int(time.time())
    entry = test_url_store.get_crawl_schedule_entry(url)

    assert entry is not None
    assert entry.status == "pending"
    assert entry.next_fetch_at >= before + 30 * 60
    assert entry.next_fetch_at <= after + 30 * 60 + 1


def test_requeue_releases_frontier_for_retry(test_url_store):
    _record_and_admit_urls(test_url_store, ["https://example.com/retry"])
    test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)

    before = int(time.time())
    requeued = test_url_store.requeue("https://example.com/retry")
    entry = test_url_store.get_crawl_schedule_entry("https://example.com/retry")
    domain_state = test_url_store.get_domain_state("example.com")

    assert requeued is True
    assert entry is not None
    assert entry.status == "pending"
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert domain_state.fail_streak == 1
    assert domain_state.backoff_until is not None
    assert domain_state.backoff_until >= before


def test_release_crawl_tasks_only_decrements_leased_domain_state(test_url_store):
    urls = [
        "https://example.com/leased-release",
        "https://example.com/pending-release",
    ]
    _record_and_admit_urls(test_url_store, urls)
    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)
    assert len(leased) == 1
    leased_url = leased[0].url
    pending_url = next(url for url in urls if url != leased_url)

    released = test_url_store.release_crawl_tasks([leased_url, pending_url])
    leased_entry = test_url_store.get_crawl_schedule_entry(leased_url)
    pending_entry = test_url_store.get_crawl_schedule_entry(pending_url)
    domain_state = test_url_store.get_domain_state("example.com")

    assert released == 2
    assert leased_entry is not None
    assert leased_entry.status == "pending"
    assert pending_entry is not None
    assert pending_entry.status == "pending"
    assert domain_state is not None
    assert domain_state.inflight_leases == 0


def test_purge_denied_domains_removes_frontier_rows(test_url_store):
    leased_url = "https://blocked.example.com/leased"
    pending_url = "https://blocked.example.com/pending"
    allowed_url = "https://allowed.example.com/keep"

    _record_and_admit_urls(test_url_store, [leased_url])
    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)
    assert [item.url for item in leased] == [leased_url]

    _record_and_admit_urls(test_url_store, [pending_url, allowed_url])

    deleted = test_url_store.purge_denied_domains(frozenset({"blocked.example.com"}))

    blocked_state = test_url_store.get_domain_state("blocked.example.com")
    allowed_entry = test_url_store.get_crawl_schedule_entry(allowed_url)

    assert deleted == 2
    assert test_url_store.get_crawl_schedule_entry(leased_url) is None
    assert test_url_store.get_crawl_schedule_entry(pending_url) is None
    assert allowed_entry is not None
    assert allowed_entry.status == "pending"
    assert blocked_state is not None
    assert blocked_state.inflight_leases == 0


def test_purge_admission_rejected_urls_removes_frontier_rows(test_url_store):
    now = int(time.time())
    frontier_url = "https://blog.hatena.ne.jp/-/share/mastodon?x=1"

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            INSERT INTO urls (url_hash, url, domain, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (url_hash) DO NOTHING
            """,
            (
                url_hash(frontier_url),
                frontier_url,
                "blog.hatena.ne.jp",
                now,
            ),
        )
        cur.execute(
            """
            INSERT INTO crawl_schedule (
                url_hash, url, domain, discovered_at,
                priority_bucket,
                status, next_fetch_at, updated_at
            )
            VALUES (%s, %s, %s, %s, 3, 'pending', %s, %s)
            """,
            (
                url_hash(frontier_url),
                frontier_url,
                "blog.hatena.ne.jp",
                now,
                now,
                now,
            ),
        )

    summary = test_url_store.purge_admission_rejected_urls(
        limit=10,
        domains=("blog.hatena.ne.jp",),
        dry_run=False,
    )

    assert summary["matched"] == 1
    assert summary["crawl_schedule_deleted"] == 1
    assert test_url_store.get_crawl_schedule_entry(frontier_url) is None


def test_crawl_task_planner_leases_from_frontier_for_real_store(test_url_store):
    _record_and_admit_urls(
        test_url_store,
        [
            "https://example.com/a",
            "https://example.org/b",
        ],
    )
    planner = CrawlTaskPlanner(
        test_url_store,
        CrawlTaskPlannerConfig(batch_size=10, lease_seconds=120),
    )

    ready = planner.lease_ready_urls(2)

    assert {item.url for item in ready} == {
        "https://example.com/a",
        "https://example.org/b",
    }
    assert (
        test_url_store.get_crawl_schedule_entry("https://example.com/a").status
        == "leased"
    )
    assert (
        test_url_store.get_crawl_schedule_entry("https://example.org/b").status
        == "leased"
    )


def test_crawl_task_planner_prefetches_past_skewed_domains(test_url_store):
    dominant = [f"https://www.debian.org/doc/{i}" for i in range(80)]
    secondary = [f"https://browse.dgit.debian.org/pkg/{i}" for i in range(30)]
    diverse = [
        "https://docs.supermemory.ai/guide",
        "https://www.lycorp.co.jp/en/",
        "https://www.rescue.ne.jp/",
        "https://metadata.ftp-master.debian.org/changelogs/",
    ]
    assert _record_and_admit_urls(
        test_url_store, dominant + secondary + diverse
    ) == len(dominant + secondary + diverse)

    now = int(time.time())
    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE crawl_schedule
            SET
                priority_bucket = 0,
                discovered_at = %s,
                next_fetch_at = %s,
                updated_at = %s
            """,
            (now, now, now),
        )

    planner = CrawlTaskPlanner(
        test_url_store,
        CrawlTaskPlannerConfig(
            batch_size=64,
            domain_max_concurrent=1,
            lease_seconds=120,
        ),
    )

    ready = planner.lease_ready_urls(4)
    domains = {item.domain for item in ready}

    assert len(ready) == 4
    assert len(domains) == 4


def test_domain_state_survives_planner_restart(test_url_store):
    _record_and_admit_urls(test_url_store, ["https://example.com/persist"])
    planner = CrawlTaskPlanner(
        test_url_store,
        CrawlTaskPlannerConfig(batch_size=10, lease_seconds=120),
    )
    leased = planner.lease_ready_urls(1)

    assert len(leased) == 1

    test_url_store.record_crawl_task_result("https://example.com/persist", "done")

    restarted = CrawlTaskPlanner(
        test_url_store,
        CrawlTaskPlannerConfig(batch_size=10, lease_seconds=120),
    )
    assert restarted.lease_ready_urls(1) == []


def test_expired_frontier_lease_is_reclaimed_on_next_pop(test_url_store):
    _record_and_admit_urls(test_url_store, ["https://example.com/expired"])
    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=1)
    assert len(leased) == 1

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE crawl_schedule
            SET lease_expires_at = %s
            WHERE url_hash = %s
            """,
            (int(time.time()) - 10, url_hash("https://example.com/expired")),
        )

    reclaimed = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=120)
    entry = test_url_store.get_crawl_schedule_entry("https://example.com/expired")
    domain_state = test_url_store.get_domain_state("example.com")

    assert [item.url for item in reclaimed] == ["https://example.com/expired"]
    assert entry is not None
    assert entry.status == "leased"
    assert domain_state is not None
    assert domain_state.inflight_leases == 1


def test_reconcile_expired_crawl_task_leases_recovers_domain_state(test_url_store):
    _record_and_admit_urls(test_url_store, ["https://example.com/expired-maintenance"])
    leased = test_url_store.lease_ready_crawl_tasks(1, lease_seconds=1)

    assert [item.url for item in leased] == ["https://example.com/expired-maintenance"]

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE crawl_schedule
            SET lease_expires_at = %s
            WHERE url_hash = %s
            """,
            (
                int(time.time()) - 5,
                url_hash("https://example.com/expired-maintenance"),
            ),
        )

    reclaimed = test_url_store.reconcile_expired_crawl_task_leases()
    entry = test_url_store.get_crawl_schedule_entry(
        "https://example.com/expired-maintenance"
    )
    domain_state = test_url_store.get_domain_state("example.com")

    assert reclaimed == 1
    assert entry is not None
    assert entry.status == "pending"
    assert domain_state is not None
    assert domain_state.inflight_leases == 0


def test_reconcile_domain_state_inflight_leases_recovers_drift(test_url_store):
    _record_and_admit_urls(test_url_store, ["https://example.com/drifted"])

    with db_transaction(test_url_store.db_path) as cur:
        test_url_store.domain_scheduling_state.ensure_domain_state_rows(
            cur,
            ["example.com"],
            now=int(time.time()),
        )
        cur.execute(
            """
            UPDATE domain_state
            SET inflight_leases = 2
            WHERE domain = %s
            """,
            ("example.com",),
        )

    repaired = test_url_store.reconcile_domain_state_inflight_leases()
    domain_state = test_url_store.get_domain_state("example.com")

    assert repaired == 1
    assert domain_state is not None
    assert domain_state.inflight_leases == 0


def test_lease_ready_crawl_tasks_ignores_stale_domain_inflight_counts(test_url_store):
    _record_and_admit_urls(test_url_store, ["https://example.com/stale"])

    with db_transaction(test_url_store.db_path) as cur:
        test_url_store.domain_scheduling_state.ensure_domain_state_rows(
            cur,
            ["example.com"],
            now=int(time.time()),
        )
        cur.execute(
            """
            UPDATE domain_state
            SET inflight_leases = 2
            WHERE domain = %s
            """,
            ("example.com",),
        )

    leased = test_url_store.lease_ready_crawl_tasks(
        1, max_per_domain=2, lease_seconds=120
    )
    domain_state = test_url_store.get_domain_state("example.com")

    assert [item.url for item in leased] == ["https://example.com/stale"]
    assert domain_state is not None
    assert domain_state.inflight_leases == 3


@pytest.mark.asyncio
async def test_process_url_non_html_200_logged_as_skipped(test_components):
    """Non-HTML 200 responses should be logged as skipped, not http_error."""
    url_store, url_ledger, link_graph, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/x-gzip"}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch(
        "web_search_crawler.services.html_processing.submit_page_to_indexer",
        new_callable=AsyncMock,
    ) as m:
        with patch(
            "web_search_crawler.workers.tasks.history_log.log_crawl_attempt"
        ) as mock_log:
            await process_url(
                mock_session,
                mock_robots,
                url_store,
                url_ledger,
                link_graph,
                planner,
                "http://example.com/archive.gz",
            )

    m.assert_not_called()
    mock_log.assert_called_once()
    args = mock_log.call_args.args
    kwargs = mock_log.call_args.kwargs
    assert args == (
        "http://example.com/archive.gz",
        "skipped",
        200,
        "Non-HTML content-type: application/x-gzip",
    )
    assert kwargs["precheck_ms"] is not None
    assert kwargs["robots_ms"] is not None
    assert kwargs["ssrf_ms"] is not None
    assert kwargs["crawl_delay_ms"] is not None
    assert kwargs["fetch_ms"] is not None
    assert kwargs["fetch_request_ms"] is not None
    assert kwargs["fetch_body_read_ms"] is None
    assert kwargs["parse_ms"] is None
    assert kwargs["submit_ms"] is None
    assert kwargs["total_ms"] is not None
    assert _url_ledger_contains(url_store, "http://example.com/archive.gz")


@pytest.mark.asyncio
async def test_process_url_logs_indexer_error_detail(test_components):
    """Indexer error details should be persisted in crawl history."""
    url_store, url_ledger, link_graph, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = AsyncMock()
    mock_response.content.read = AsyncMock(
        return_value=b"<html><head><title>T</title></head><body>C</body></html>"
    )
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch(
        "web_search_crawler.services.html_processing.parse_page",
        return_value=ParsedDocument(
            title="T",
            content="content",
            outlinks=[],
        ),
    ):
        with patch(
            "web_search_crawler.services.html_processing.submit_page_to_indexer",
            new_callable=AsyncMock,
        ) as mock_indexer:
            with patch(
                "web_search_crawler.workers.tasks.history_log.log_crawl_attempt"
            ) as mock_log:
                mock_indexer.return_value = IndexerSubmitResult(
                    ok=False,
                    status_code=422,
                    detail="Indexer 422: url_too_long",
                )
                await process_url(
                    mock_session,
                    mock_robots,
                    url_store,
                    url_ledger,
                    link_graph,
                    planner,
                    "http://example.com/fail",
                )

    assert any(
        call.args
        == (
            "http://example.com/fail",
            "indexer_error",
            422,
            "Indexer 422: url_too_long",
        )
        and call.kwargs["precheck_ms"] is not None
        and call.kwargs["robots_ms"] is not None
        and call.kwargs["ssrf_ms"] is not None
        and call.kwargs["crawl_delay_ms"] is not None
        and call.kwargs["fetch_ms"] is not None
        and call.kwargs["fetch_request_ms"] is not None
        and call.kwargs["fetch_body_read_ms"] is not None
        and call.kwargs["parse_ms"] is not None
        and call.kwargs["submit_ms"] is not None
        and call.kwargs["total_ms"] is not None
        for call in mock_log.call_args_list
    )
    assert _url_ledger_contains(url_store, "http://example.com/fail")


@pytest.mark.asyncio
async def test_process_url_retry_returns_url_to_frontier(test_components):
    """Verify retry returns URL to the frontier via requeue."""
    url_store, url_ledger, link_graph, planner = test_components
    test_url = "http://example.com/retry-test"

    # Add and lease to simulate real flow
    _record_and_admit_url(url_store, test_url)
    popped = url_store.lease_ready_crawl_tasks(1)
    assert len(popped) == 1
    entry = url_store.get_crawl_schedule_entry(test_url)
    assert entry is not None
    assert entry.status == "leased"

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = True
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    # Mock network error to trigger retry
    import aiohttp

    mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

    with patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            test_url,
        )

    # URL should be back in the frontier after retry
    entry = url_store.get_crawl_schedule_entry(test_url)
    assert entry is not None
    assert entry.status == "pending"


def test_requeue_releases_leased_url_back_to_pending(tmp_path):
    """requeue should release a leased frontier URL back to pending."""
    url_store = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    _record_and_admit_url(url_store, "http://example.com/r")
    url_store.lease_ready_crawl_tasks(1)

    result = url_store.requeue("http://example.com/r")
    assert result is True

    entry = url_store.get_crawl_schedule_entry("http://example.com/r")
    assert entry is not None
    assert entry.status == "pending"


def test_store_bootstrap_keeps_runtime_rows_without_frontier_domain_backfill(tmp_path):
    url_store = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    _record_and_admit_urls(url_store, ["https://example.com/bootstrap"])

    from web_search_crawler.db.connection import db_transaction

    with db_transaction(url_store.db_path) as cur:
        cur.execute("TRUNCATE domain_state")

    restarted = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    domain_state = restarted.get_domain_state("example.com")
    assert domain_state is None


def test_requeue_noop_if_already_queued(tmp_path):
    """requeue should be a no-op if URL is already pending in frontier."""
    url_store = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    _record_and_admit_url(url_store, "http://example.com/noop")

    # Already pending in frontier, requeue should conflict
    result = url_store.requeue("http://example.com/noop")
    assert result is False


def test_lease_ready_crawl_tasks_respects_max_per_domain(tmp_path):
    """Frontier leasing should cap leases per domain."""
    url_store = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    urls = [
        "http://a.example.com/1",
        "http://a.example.com/2",
        "http://a.example.com/3",
        "http://a.example.com/4",
        "http://b.example.com/1",
        "http://b.example.com/2",
        "http://c.example.com/1",
    ]
    assert _record_and_admit_urls(url_store, urls) == len(urls)

    popped = url_store.lease_ready_crawl_tasks(5, max_per_domain=2)

    assert len(popped) == 5

    per_domain: dict[str, int] = {}
    for item in popped:
        per_domain[item.domain] = per_domain.get(item.domain, 0) + 1

    assert per_domain["a.example.com"] == 2
    assert max(per_domain.values()) <= 2
    popped_urls = {item.url for item in popped}
    for url in urls:
        entry = url_store.get_crawl_schedule_entry(url)
        assert entry is not None
        assert entry.status == ("leased" if url in popped_urls else "pending")


def test_record_and_admit_deduplicates_urls(tmp_path):
    """record_and_admit_urls should deduplicate URLs within the same batch."""
    url_store = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    urls = [
        "http://example.com/1",
        "http://example.com/1",
        "http://example.com/2",
        "http://example.com/2",
    ]

    assert _record_and_admit_urls(url_store, urls) == 2

    assert _url_ledger_contains(url_store, "http://example.com/1")
    assert _url_ledger_contains(url_store, "http://example.com/2")
    entry_1 = url_store.get_crawl_schedule_entry("http://example.com/1")
    entry_2 = url_store.get_crawl_schedule_entry("http://example.com/2")
    assert entry_1 is not None
    assert entry_1.status == "pending"
    assert entry_2 is not None
    assert entry_2.status == "pending"


def test_record_and_admit_retries_db_concurrency_error(tmp_path):
    """record_and_admit_urls should retry once on DB concurrency errors."""
    url_store = CrawlerRuntimeStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    original = url_store._schedule_urls_for_crawl_chunk
    calls = 0

    def flaky_schedule_urls_for_crawl_chunk(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise DeadlockDetected()
        return original(*args, **kwargs)

    url_store._schedule_urls_for_crawl_chunk = flaky_schedule_urls_for_crawl_chunk

    assert _record_and_admit_urls(url_store, ["http://example.com/retry"]) == 1
    assert calls == 2
    entry = url_store.get_crawl_schedule_entry("http://example.com/retry")
    assert entry is not None
    assert entry.status == "pending"


def test_record_and_admit_collapses_tracking_param_variants(test_url_store):
    added = _record_and_admit_urls(
        test_url_store,
        [
            "https://example.com/docs?id=1&utm_source=x",
            "https://example.com/docs?id=1",
        ],
    )

    entry = test_url_store.get_crawl_schedule_entry("https://example.com/docs?id=1")

    assert added == 1
    assert entry is not None
    assert entry.url == "https://example.com/docs?id=1"
    assert entry.status == "pending"


def test_record_and_admit_rejects_low_value_admission_urls(test_url_store):
    added = _record_and_admit_urls(test_url_store, ["https://example.com/login"])

    assert added == 0
    assert test_url_store.get_crawl_schedule_entry("https://example.com/login") is None


@pytest.mark.asyncio
async def test_process_url_too_long_is_skipped_before_fetch(test_components):
    """Overly long URLs should be skipped before robots/fetch/indexer."""
    from web_search_core.utils import MAX_URL_LENGTH

    url_store, url_ledger, link_graph, planner = test_components
    over_limit_url = "http://example.com/" + ("a" * MAX_URL_LENGTH)

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    with patch(
        "web_search_crawler.workers.tasks.history_log.log_crawl_attempt"
    ) as mock_log:
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            url_ledger,
            link_graph,
            planner,
            over_limit_url,
        )

    mock_robots.can_fetch.assert_not_called()
    mock_session.get.assert_not_called()
    assert mock_log.call_args.args[0] == over_limit_url
    assert mock_log.call_args.args[1] == "skipped"
    assert "URL too long:" in mock_log.call_args.kwargs["error_message"]
    assert _url_ledger_contains(url_store, over_limit_url)
