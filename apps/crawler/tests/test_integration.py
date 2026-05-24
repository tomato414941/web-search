"""
Integration Tests

End-to-end tests for the full crawler workflow.
"""

import time

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from psycopg2.errors import DeadlockDetected

from web_search_crawler.db import UrlStore
from web_search_crawler.db.connection import db_transaction
from web_search_crawler.db.url_types import url_hash
from web_search_crawler.frontier_planner import FrontierPlanner, FrontierPlannerConfig
from web_search_crawler.services.crawl_policy import compute_failure_retry_delay
from web_search_crawler.services.direct_crawl import crawl_url_now
from web_search_crawler.services.frontier import FrontierService
from web_search_crawler.services.seeds import SeedService
from web_search_crawler.services.indexer import IndexerSubmitResult
from web_search_crawler.utils.parser import ParsedDocument
from web_search_crawler.workers.types import PipelineProcessResult
from web_search_crawler.workers.tasks import process_url


@pytest.fixture
def test_components(tmp_path):
    """Create test UrlStore and frontier planner."""
    db_path = str(tmp_path / "test.db")
    url_store = UrlStore(db_path, recrawl_after_days=30)
    planner = FrontierPlanner(url_store, FrontierPlannerConfig())
    return url_store, planner


@pytest.mark.asyncio
async def test_process_url_success_flow(test_components):
    """Test complete process_url flow with successful indexing"""
    url_store, planner = test_components

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
                assert url_store.contains("http://example.com/test")


@pytest.mark.asyncio
async def test_process_url_robots_blocked(test_components):
    """Test process_url when robots.txt blocks URL"""
    url_store, planner = test_components

    mock_session = MagicMock()
    mock_robots = AsyncMock()
    mock_robots.can_fetch.return_value = False  # Blocked
    mock_robots.get_crawl_delay = MagicMock(return_value=None)

    with patch("web_search_crawler.workers.tasks.history_log.log_crawl_attempt"):
        await process_url(
            mock_session,
            mock_robots,
            url_store,
            planner,
            "http://example.com/blocked",
        )

        # Should not fetch
        mock_session.get.assert_not_called()

        # URL should be recorded as failed
        assert url_store.contains("http://example.com/blocked")


@pytest.mark.asyncio
async def test_process_url_http_error(test_components):
    """Test process_url with HTTP error (404)"""
    url_store, planner = test_components

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
            planner,
            "http://example.com/notfound",
        )

        # URL should be recorded as failed
        assert url_store.contains("http://example.com/notfound")


@pytest.mark.asyncio
async def test_process_url_network_error(test_components):
    """Test process_url with network error returning the URL to the frontier."""
    url_store, planner = test_components
    test_url = "http://example.com/error"

    # Add URL to frontier then lease it (simulates real flow)
    url_store.discover_and_admit_url(test_url)
    url_store.pop_frontier_batch(1)

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
            planner,
            test_url,
        )

        # URL should be returned to pending frontier state for retry
        stats = url_store.get_stats()
        assert stats["pending"] == 1


@pytest.mark.asyncio
async def test_process_url_discovers_links(test_components):
    """Test that process_url adds discovered links to url_store"""
    url_store, planner = test_components

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
                    planner,
                    "http://example.com/",
                )

                # Discovered links should be in url_store
                assert url_store.contains("http://example.com/link1")
                assert url_store.contains("http://example.com/link2")


def test_discover_and_admit_populates_frontier_entry_for_outlinks(test_url_store):
    added = test_url_store.discover_and_admit_urls(["http://example.com/1"])

    entry = test_url_store.get_frontier_entry("http://example.com/1")
    domain_state = test_url_store.get_domain_state("example.com")

    assert added == 1
    assert test_url_store.frontier_count() == 1
    assert entry is not None
    assert entry.discovered_via == "outlink"
    assert entry.crawl_profile == "generic"
    assert entry.status == "pending"
    assert domain_state is not None


def test_record_discovered_urls_writes_ledger_without_frontier(test_url_store):
    recorded = test_url_store.record_discovered_urls(
        ["https://example.com/article-entry"],
        discovered_via="feed_entry",
    )

    assert recorded == 1
    assert test_url_store.contains("https://example.com/article-entry")
    assert (
        test_url_store.get_frontier_entry("https://example.com/article-entry") is None
    )
    assert test_url_store.frontier_count() == 0


def test_pop_frontier_batch_retries_after_deadlock(test_url_store, monkeypatch):
    test_url_store.discover_and_admit_urls(["http://example.com/frontier"])

    original = test_url_store._lease_frontier_candidates
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise DeadlockDetected("deadlock detected")
        return original(*args, **kwargs)

    monkeypatch.setattr(test_url_store, "_lease_frontier_candidates", flaky)

    leased = test_url_store.pop_frontier_batch(1, lease_seconds=120)

    assert [item.url for item in leased] == ["http://example.com/frontier"]
    assert calls["count"] >= 2


def test_pop_frontier_batch_leases_url_and_clears_pending_frontier_state(
    test_url_store,
):
    test_url_store.discover_and_admit_urls(["http://example.com/frontier"])

    leased = test_url_store.pop_frontier_batch(1, lease_seconds=120)
    entry = test_url_store.get_frontier_entry("http://example.com/frontier")
    domain_state = test_url_store.get_domain_state("example.com")

    assert [item.url for item in leased] == ["http://example.com/frontier"]
    assert entry is not None
    assert entry.status == "leased"
    assert test_url_store.pending_count() == 0
    assert domain_state is not None
    assert domain_state.inflight_leases == 1


def test_pop_frontier_batch_reserves_slots_across_budget_tiers(test_url_store):
    urls = [
        "https://docs.python.org/3/whatsnew/3.13.html",
        "https://kubernetes.io/docs/",
        "https://example.com/a-generic-page",
    ]
    test_url_store.discover_and_admit_urls(urls)

    leased = test_url_store.pop_frontier_batch(2, lease_seconds=120)

    assert {item.url for item in leased} == {
        "https://docs.python.org/3/whatsnew/3.13.html",
        "https://kubernetes.io/docs/",
    }


def test_pop_frontier_batch_redistributes_unused_budget_to_bulk(test_url_store):
    urls = [
        "https://example.com/a-generic-page",
        "https://example.org/another-generic-page",
    ]
    test_url_store.discover_and_admit_urls(urls)

    leased = test_url_store.pop_frontier_batch(2, lease_seconds=120)

    assert {item.url for item in leased} == set(urls)


def test_pop_frontier_batch_does_not_duplicate_tier_fallback_leases(test_url_store):
    urls = [
        "https://example.com/only-generic",
        "https://example.org/also-generic",
    ]
    test_url_store.discover_and_admit_urls(urls)

    leased = test_url_store.pop_frontier_batch(4, lease_seconds=120)
    leased_urls = [item.url for item in leased]

    assert sorted(leased_urls) == sorted(urls)
    assert len(leased_urls) == len(set(leased_urls))
    assert test_url_store.pending_count() == 0


def test_pop_frontier_batch_skips_domains_blocked_by_domain_state(test_url_store):
    blocked = "https://blocked.example.com/page"
    ready = "https://ready.example.com/page"
    test_url_store.discover_and_admit_urls([blocked, ready])
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

    leased = test_url_store.pop_frontier_batch(1, lease_seconds=120)

    assert [item.url for item in leased] == [ready]


def test_record_updates_frontier_after_success(test_url_store):
    test_url_store.discover_and_admit_urls(
        ["https://docs.docker.com/reference/cli/docker/"]
    )
    test_url_store.pop_frontier_batch(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_result(
        "https://docs.docker.com/reference/cli/docker/",
        "done",
    )
    after = int(time.time())
    entry = test_url_store.get_frontier_entry(
        "https://docs.docker.com/reference/cli/docker/"
    )
    domain_state = test_url_store.get_domain_state("docs.docker.com")

    assert entry is not None
    assert entry.status == "pending"
    assert entry.next_fetch_at >= before + 5 * 24 * 3600
    assert entry.next_fetch_at <= after + 5 * 24 * 3600 + 1
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert domain_state.fail_streak == 0
    assert domain_state.next_request_at >= before


def test_record_failure_updates_frontier_and_domain_state(test_url_store):
    url = "https://example.com/failure"
    test_url_store.discover_and_admit_urls([url])
    test_url_store.pop_frontier_batch(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_result(url, "failed")
    after = int(time.time())
    entry = test_url_store.get_frontier_entry(url)
    domain_state = test_url_store.get_domain_state("example.com")
    counters = test_url_store.get_frontier_counters()

    assert entry is not None
    assert entry.status == "pending"
    retry_delay = compute_failure_retry_delay("generic", fail_streak=0)
    assert entry.next_fetch_at >= before + retry_delay
    assert entry.next_fetch_at <= after + retry_delay + 1
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert domain_state.fail_streak == 1
    assert domain_state.backoff_until is not None
    assert domain_state.backoff_until >= before
    assert counters == {
        "pending_rows": 1,
        "leased_rows": 0,
        "frontier_rows": 1,
    }


def test_seed_success_uses_shorter_recrawl_interval(test_url_store):
    service = SeedService(test_url_store)
    service.add_seeds(["https://docs.docker.com/"])
    test_url_store.pop_frontier_batch(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_result("https://docs.docker.com/", "done")
    after = int(time.time())
    entry = test_url_store.get_frontier_entry("https://docs.docker.com/")

    assert entry is not None
    assert entry.next_fetch_at >= before + 3 * 24 * 3600
    assert entry.next_fetch_at <= after + 3 * 24 * 3600 + 1


def test_manual_success_reclassifies_to_normal_crawl_policy(test_url_store):
    url = "https://docs.docker.com/reference/cli/docker/"
    test_url_store.discover_and_admit_urls([url], discovered_via="manual")
    test_url_store.pop_frontier_batch(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_result(url, "done")
    after = int(time.time())
    entry = test_url_store.get_frontier_entry(url)

    assert entry is not None
    assert entry.status == "pending"
    assert entry.crawl_profile == "canonical_docs"
    assert entry.canonical_source == "docker_docs"
    assert entry.priority_bucket == 1
    assert entry.next_fetch_at >= before + 5 * 24 * 3600
    assert entry.next_fetch_at <= after + 5 * 24 * 3600 + 1


def test_release_notes_failure_retries_quickly(test_url_store):
    url = "https://docs.python.org/3/whatsnew/3.13.html"
    test_url_store.discover_and_admit_urls([url])
    test_url_store.pop_frontier_batch(1, lease_seconds=120)

    before = int(time.time())
    test_url_store.record_crawl_result(url, "failed")
    after = int(time.time())
    entry = test_url_store.get_frontier_entry(url)

    assert entry is not None
    assert entry.status == "pending"
    assert entry.next_fetch_at >= before + 30 * 60
    assert entry.next_fetch_at <= after + 30 * 60 + 1


def test_seed_service_populates_frontier_entry_as_seed(test_url_store):
    service = SeedService(test_url_store)

    added = service.add_seeds(["https://docs.docker.com/"])

    entry = test_url_store.get_frontier_entry("https://docs.docker.com/")

    assert added == 1
    assert entry is not None
    assert entry.is_seed is True
    assert entry.discovered_via == "seed"
    assert entry.priority_bucket <= 1
    assert entry.canonical_source == "docker_docs"


@pytest.mark.asyncio
async def test_frontier_service_populates_frontier_entry_as_manual(test_url_store):
    service = FrontierService(test_url_store)

    added = await service.admit_urls(["https://example.com/manual"])

    entry = test_url_store.get_frontier_entry("https://example.com/manual")

    assert added == 1
    assert entry is not None
    assert entry.discovered_via == "manual"
    assert entry.crawl_profile == "manual_now"
    assert entry.priority_bucket == 0


def test_requeue_releases_frontier_for_retry(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/retry"])
    test_url_store.pop_frontier_batch(1, lease_seconds=120)

    before = int(time.time())
    requeued = test_url_store.requeue("https://example.com/retry")
    entry = test_url_store.get_frontier_entry("https://example.com/retry")
    domain_state = test_url_store.get_domain_state("example.com")

    assert requeued is True
    assert entry is not None
    assert entry.status == "pending"
    assert test_url_store.pending_count() == 1
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert domain_state.fail_streak == 1
    assert domain_state.backoff_until is not None
    assert domain_state.backoff_until >= before


def test_release_frontier_urls_only_decrements_leased_domain_state(test_url_store):
    urls = [
        "https://example.com/leased-release",
        "https://example.com/pending-release",
    ]
    test_url_store.discover_and_admit_urls(urls)
    leased = test_url_store.pop_frontier_batch(1, lease_seconds=120)
    assert len(leased) == 1
    leased_url = leased[0].url
    pending_url = next(url for url in urls if url != leased_url)

    released = test_url_store.release_frontier_urls([leased_url, pending_url])
    leased_entry = test_url_store.get_frontier_entry(leased_url)
    pending_entry = test_url_store.get_frontier_entry(pending_url)
    domain_state = test_url_store.get_domain_state("example.com")
    counters = test_url_store.get_frontier_counters()

    assert released == 2
    assert leased_entry is not None
    assert leased_entry.status == "pending"
    assert pending_entry is not None
    assert pending_entry.status == "pending"
    assert domain_state is not None
    assert domain_state.inflight_leases == 0
    assert counters == {
        "pending_rows": 2,
        "leased_rows": 0,
        "frontier_rows": 2,
    }


def test_purge_denied_domains_removes_frontier_rows(test_url_store):
    leased_url = "https://blocked.example.com/leased"
    pending_url = "https://blocked.example.com/pending"
    allowed_url = "https://allowed.example.com/keep"

    test_url_store.discover_and_admit_urls([leased_url])
    leased = test_url_store.pop_frontier_batch(1, lease_seconds=120)
    assert [item.url for item in leased] == [leased_url]

    test_url_store.discover_and_admit_urls([pending_url, allowed_url])

    deleted = test_url_store.purge_denied_domains(frozenset({"blocked.example.com"}))

    blocked_state = test_url_store.get_domain_state("blocked.example.com")
    allowed_entry = test_url_store.get_frontier_entry(allowed_url)

    assert deleted == 2
    assert test_url_store.get_frontier_entry(leased_url) is None
    assert test_url_store.get_frontier_entry(pending_url) is None
    assert test_url_store.pending_count() == 1
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
            INSERT INTO urls (url_hash, url, domain, created_at, is_seed)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (url_hash) DO NOTHING
            """,
            (
                url_hash(frontier_url),
                frontier_url,
                "blog.hatena.ne.jp",
                now,
                False,
            ),
        )
        cur.execute(
            """
            INSERT INTO frontier_entries (
                url_hash, url, domain, normalized_url, discovered_at, discovered_via,
                discovery_depth, is_seed, canonical_source, crawl_profile,
                priority_bucket, priority_score, status, next_fetch_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'outlink', 1, FALSE, NULL, 'generic', 3, 0, 'pending', %s, %s)
            """,
            (
                url_hash(frontier_url),
                frontier_url,
                "blog.hatena.ne.jp",
                frontier_url,
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
    assert summary["frontier_deleted"] == 1
    assert test_url_store.get_frontier_entry(frontier_url) is None


def test_frontier_planner_leases_from_frontier_for_real_store(test_url_store):
    test_url_store.discover_and_admit_urls(
        [
            "https://example.com/a",
            "https://example.org/b",
        ]
    )
    planner = FrontierPlanner(
        test_url_store,
        FrontierPlannerConfig(batch_size=10, lease_seconds=120),
    )

    ready = planner.lease_ready_urls(2)

    assert {item.url for item in ready} == {
        "https://example.com/a",
        "https://example.org/b",
    }
    assert test_url_store.pending_count() == 0
    assert test_url_store.get_frontier_entry("https://example.com/a").status == "leased"


def test_frontier_planner_prefetches_past_skewed_domains(test_url_store):
    dominant = [f"https://www.debian.org/doc/{i}" for i in range(80)]
    secondary = [f"https://browse.dgit.debian.org/pkg/{i}" for i in range(30)]
    diverse = [
        "https://docs.supermemory.ai/guide",
        "https://www.lycorp.co.jp/en/",
        "https://www.rescue.ne.jp/",
        "https://metadata.ftp-master.debian.org/changelogs/",
    ]
    assert test_url_store.discover_and_admit_urls(
        dominant + secondary + diverse
    ) == len(dominant + secondary + diverse)

    now = int(time.time())
    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE frontier_entries
            SET
                priority_bucket = 0,
                priority_score = CASE
                    WHEN domain = 'www.debian.org' THEN 100
                    WHEN domain = 'browse.dgit.debian.org' THEN 90
                    ELSE 10
                END,
                discovered_at = %s,
                next_fetch_at = %s,
                updated_at = %s
            """,
            (now, now, now),
        )

    planner = FrontierPlanner(
        test_url_store,
        FrontierPlannerConfig(
            batch_size=64,
            domain_max_concurrent=1,
            lease_seconds=120,
        ),
    )

    ready = planner.lease_ready_urls(4)
    domains = {item.domain for item in ready}

    assert len(ready) == 4
    assert len(domains) == 4
    assert "www.debian.org" in domains
    assert "browse.dgit.debian.org" in domains


def test_domain_state_survives_planner_restart(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/persist"])
    planner = FrontierPlanner(
        test_url_store,
        FrontierPlannerConfig(batch_size=10, lease_seconds=120),
    )
    leased = planner.lease_ready_urls(1)

    assert len(leased) == 1

    test_url_store.record_crawl_result("https://example.com/persist", "done")

    restarted = FrontierPlanner(
        test_url_store,
        FrontierPlannerConfig(batch_size=10, lease_seconds=120),
    )
    assert restarted.lease_ready_urls(1) == []


def test_expired_frontier_lease_is_reclaimed_on_next_pop(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/expired"])
    leased = test_url_store.pop_frontier_batch(1, lease_seconds=1)
    assert len(leased) == 1

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE frontier_entries
            SET lease_expires_at = %s
            WHERE url_hash = %s
            """,
            (int(time.time()) - 10, url_hash("https://example.com/expired")),
        )

    reclaimed = test_url_store.pop_frontier_batch(1, lease_seconds=120)
    entry = test_url_store.get_frontier_entry("https://example.com/expired")
    domain_state = test_url_store.get_domain_state("example.com")

    assert [item.url for item in reclaimed] == ["https://example.com/expired"]
    assert entry is not None
    assert entry.status == "leased"
    assert domain_state is not None
    assert domain_state.inflight_leases == 1


def test_reconcile_expired_frontier_leases_recovers_domain_state(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/expired-maintenance"])
    leased = test_url_store.pop_frontier_batch(1, lease_seconds=1)

    assert [item.url for item in leased] == ["https://example.com/expired-maintenance"]

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE frontier_entries
            SET lease_expires_at = %s
            WHERE url_hash = %s
            """,
            (
                int(time.time()) - 5,
                url_hash("https://example.com/expired-maintenance"),
            ),
        )

    reclaimed = test_url_store.reconcile_expired_frontier_leases()
    entry = test_url_store.get_frontier_entry("https://example.com/expired-maintenance")
    domain_state = test_url_store.get_domain_state("example.com")

    assert reclaimed == 1
    assert entry is not None
    assert entry.status == "pending"
    assert domain_state is not None
    assert domain_state.inflight_leases == 0


def test_reconcile_expired_frontier_leases_updates_counters(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/expired-counters"])
    leased = test_url_store.pop_frontier_batch(1, lease_seconds=1)
    assert [item.url for item in leased] == ["https://example.com/expired-counters"]

    with db_transaction(test_url_store.db_path) as cur:
        cur.execute(
            """
            UPDATE frontier_entries
            SET lease_expires_at = %s
            WHERE url_hash = %s
            """,
            (
                int(time.time()) - 5,
                url_hash("https://example.com/expired-counters"),
            ),
        )

    assert test_url_store.reconcile_expired_frontier_leases() == 1

    assert test_url_store.get_frontier_counters() == {
        "pending_rows": 1,
        "leased_rows": 0,
        "frontier_rows": 1,
    }


def test_reconcile_domain_state_inflight_leases_recovers_drift(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/drifted"])

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


def test_pop_frontier_batch_ignores_stale_domain_inflight_counts(test_url_store):
    test_url_store.discover_and_admit_urls(["https://example.com/stale"])

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

    leased = test_url_store.pop_frontier_batch(1, max_per_domain=2, lease_seconds=120)
    domain_state = test_url_store.get_domain_state("example.com")

    assert [item.url for item in leased] == ["https://example.com/stale"]
    assert domain_state is not None
    assert domain_state.inflight_leases == 3


def test_lease_manual_url_promotes_frontier_entry(test_url_store):
    leased = test_url_store.lease_manual_url("https://example.com/manual-now")
    entry = test_url_store.get_frontier_entry("https://example.com/manual-now")
    domain_state = test_url_store.get_domain_state("example.com")

    assert leased is True
    assert entry is not None
    assert entry.discovered_via == "manual"
    assert entry.crawl_profile == "manual_now"
    assert entry.status == "leased"
    assert domain_state is not None
    assert domain_state.inflight_leases == 1


@pytest.mark.asyncio
async def test_crawl_url_now_returns_busy_for_already_leased_url(test_url_store):
    assert test_url_store.lease_manual_url("https://example.com/already-leased") is True

    result = await crawl_url_now(
        "https://example.com/already-leased",
        url_store=test_url_store,
    )

    assert result.status == "busy"
    assert result.message == "URL is already leased by another crawl"


@pytest.mark.asyncio
async def test_crawl_url_now_maps_internal_success_to_submitted(test_url_store):
    with (
        patch(
            "web_search_crawler.services.direct_crawl.execute_crawl",
            new=AsyncMock(
                return_value=PipelineProcessResult(
                    status="queued_for_index",
                    message="Page queued for indexing",
                    job_id="job-123",
                    outlinks_discovered=2,
                )
            ),
        ),
        patch(
            "web_search_crawler.services.direct_crawl.load_static_crawl_config",
            return_value=(frozenset(), None),
        ),
    ):
        result = await crawl_url_now(
            "https://example.com/direct-success",
            url_store=test_url_store,
        )

    assert result.status == "submitted"
    assert result.message == "Page submitted to indexer"
    assert result.job_id == "job-123"
    assert result.outlinks_discovered == 2


@pytest.mark.asyncio
async def test_crawl_url_now_maps_internal_retry_to_failed(test_url_store):
    with (
        patch(
            "web_search_crawler.services.direct_crawl.execute_crawl",
            new=AsyncMock(
                return_value=PipelineProcessResult(
                    status="retry",
                    message="HTTP 429",
                    outlinks_discovered=0,
                )
            ),
        ),
        patch(
            "web_search_crawler.services.direct_crawl.load_static_crawl_config",
            return_value=(frozenset(), None),
        ),
    ):
        result = await crawl_url_now(
            "https://example.com/direct-retry",
            url_store=test_url_store,
        )

    assert result.status == "failed"
    assert result.message == "HTTP 429"
    assert result.job_id is None


@pytest.mark.asyncio
async def test_process_url_non_html_200_logged_as_skipped(test_components):
    """Non-HTML 200 responses should be logged as skipped, not http_error."""
    url_store, planner = test_components

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
    assert url_store.contains("http://example.com/archive.gz")


@pytest.mark.asyncio
async def test_process_url_logs_indexer_error_detail(test_components):
    """Indexer error details should be persisted in crawl history."""
    url_store, planner = test_components

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
    assert url_store.contains("http://example.com/fail")


@pytest.mark.asyncio
async def test_process_url_retry_returns_url_to_frontier(test_components):
    """Verify retry returns URL to the frontier via requeue."""
    url_store, planner = test_components
    test_url = "http://example.com/retry-test"

    # Add and lease to simulate real flow
    url_store.discover_and_admit_url(test_url)
    popped = url_store.pop_frontier_batch(1)
    assert len(popped) == 1
    stats = url_store.get_stats()
    assert stats["pending"] == 0

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
            planner,
            test_url,
        )

    # URL should be back in the frontier after retry
    stats = url_store.get_stats()
    assert stats["pending"] == 1, f"Expected pending=1, got {stats}"


def test_requeue_releases_leased_url_back_to_pending(tmp_path):
    """requeue should release a leased frontier URL back to pending."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    url_store.discover_and_admit_url("http://example.com/r")
    url_store.pop_frontier_batch(1)

    result = url_store.requeue("http://example.com/r")
    assert result is True

    stats = url_store.get_stats()
    assert stats["pending"] == 1


def test_get_stats_cache_is_invalidated_on_mutation(tmp_path):
    """get_stats should refresh after frontier mutations."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    assert url_store.get_stats()["pending"] == 0
    assert url_store.discover_and_admit_url("http://example.com/cache") is True
    assert url_store.get_stats()["pending"] == 1

    url_store.pop_frontier_batch(1)
    assert url_store.get_stats()["pending"] == 0


def test_frontier_counters_track_status_transitions(test_url_store):
    assert test_url_store.get_frontier_counters() == {
        "pending_rows": 0,
        "leased_rows": 0,
        "frontier_rows": 0,
    }

    test_url_store.discover_and_admit_urls(["https://example.com/counters"])
    assert test_url_store.get_frontier_counters() == {
        "pending_rows": 1,
        "leased_rows": 0,
        "frontier_rows": 1,
    }

    leased = test_url_store.pop_frontier_batch(1, lease_seconds=120)
    assert [item.url for item in leased] == ["https://example.com/counters"]
    assert test_url_store.get_frontier_counters() == {
        "pending_rows": 0,
        "leased_rows": 1,
        "frontier_rows": 1,
    }

    assert test_url_store.requeue("https://example.com/counters") is True
    assert test_url_store.get_frontier_counters() == {
        "pending_rows": 1,
        "leased_rows": 0,
        "frontier_rows": 1,
    }


def test_frontier_counters_are_read_side_in_prod_shape(tmp_path):
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    url_store.frontier_admin_state._refresh_interval_sec = 3600

    assert url_store.get_frontier_counters() == {
        "pending_rows": 0,
        "leased_rows": 0,
        "frontier_rows": 0,
    }

    assert url_store.discover_and_admit_url("https://example.com/read-side") is True
    assert url_store.get_frontier_counters() == {
        "pending_rows": 0,
        "leased_rows": 0,
        "frontier_rows": 0,
    }

    assert url_store.rebuild_frontier_counters() == {
        "pending_rows": 1,
        "leased_rows": 0,
        "frontier_rows": 1,
    }


def test_store_bootstrap_keeps_runtime_rows_without_frontier_domain_backfill(tmp_path):
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    url_store.discover_and_admit_urls(["https://example.com/bootstrap"])

    from web_search_crawler.db.connection import db_transaction

    with db_transaction(url_store.db_path) as cur:
        cur.execute("TRUNCATE frontier_counters, domain_state")

    restarted = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    assert restarted.get_frontier_counters() == {
        "pending_rows": 1,
        "leased_rows": 0,
        "frontier_rows": 1,
    }
    domain_state = restarted.get_domain_state("example.com")
    assert domain_state is None


def test_requeue_noop_if_already_queued(tmp_path):
    """requeue should be a no-op if URL is already pending in frontier."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)
    url_store.discover_and_admit_url("http://example.com/noop")

    # Already pending in frontier, requeue should conflict
    result = url_store.requeue("http://example.com/noop")
    assert result is False


def test_pop_frontier_batch_respects_max_per_domain(tmp_path):
    """Frontier leasing should cap leases per domain."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    urls = [
        "http://a.example.com/1",
        "http://a.example.com/2",
        "http://a.example.com/3",
        "http://a.example.com/4",
        "http://b.example.com/1",
        "http://b.example.com/2",
        "http://c.example.com/1",
    ]
    assert url_store.discover_and_admit_urls(urls) == len(urls)

    popped = url_store.pop_frontier_batch(5, max_per_domain=2)

    assert len(popped) == 5

    per_domain: dict[str, int] = {}
    for item in popped:
        per_domain[item.domain] = per_domain.get(item.domain, 0) + 1

    assert per_domain["a.example.com"] == 2
    assert max(per_domain.values()) <= 2
    assert url_store.get_stats()["pending"] == len(urls) - len(popped)


def test_discover_and_admit_deduplicates_urls(tmp_path):
    """discover_and_admit_urls should deduplicate URLs within the same batch."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    urls = [
        "http://example.com/1",
        "http://example.com/1",
        "http://example.com/2",
        "http://example.com/2",
    ]

    assert url_store.discover_and_admit_urls(urls) == 2

    stats = url_store.get_stats()
    assert stats["pending"] == 2
    assert url_store.contains("http://example.com/1")
    assert url_store.contains("http://example.com/2")


def test_discover_and_admit_retries_db_concurrency_error(tmp_path):
    """discover_and_admit_urls should retry once on DB concurrency errors."""
    url_store = UrlStore(str(tmp_path / "test.db"), recrawl_after_days=30)

    original = url_store._admit_urls_to_frontier_chunk
    calls = 0

    def flaky_admit_urls_to_frontier_chunk(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise DeadlockDetected()
        return original(*args, **kwargs)

    url_store._admit_urls_to_frontier_chunk = flaky_admit_urls_to_frontier_chunk

    assert url_store.discover_and_admit_urls(["http://example.com/retry"]) == 1
    assert calls == 2
    assert url_store.get_stats()["pending"] == 1


def test_discover_and_admit_collapses_tracking_param_variants(test_url_store):
    added = test_url_store.discover_and_admit_urls(
        [
            "https://example.com/docs?id=1&utm_source=x",
            "https://example.com/docs?id=1",
        ]
    )

    entry = test_url_store.get_frontier_entry("https://example.com/docs?id=1")

    assert added == 1
    assert entry is not None
    assert entry.url == "https://example.com/docs?id=1"
    assert test_url_store.pending_count() == 1


def test_discover_and_admit_rejects_low_value_admission_urls(test_url_store):
    added = test_url_store.discover_and_admit_urls(["https://example.com/login"])

    assert added == 0
    assert test_url_store.get_frontier_entry("https://example.com/login") is None
    assert test_url_store.pending_count() == 0


@pytest.mark.asyncio
async def test_process_url_too_long_is_skipped_before_fetch(test_components):
    """Overly long URLs should be skipped before robots/fetch/indexer."""
    from web_search_core.utils import MAX_URL_LENGTH

    url_store, planner = test_components
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
            planner,
            over_limit_url,
        )

    mock_robots.can_fetch.assert_not_called()
    mock_session.get.assert_not_called()
    assert mock_log.call_args.args[0] == over_limit_url
    assert mock_log.call_args.args[1] == "skipped"
    assert "URL too long:" in mock_log.call_args.kwargs["error_message"]
    assert url_store.contains(over_limit_url)
