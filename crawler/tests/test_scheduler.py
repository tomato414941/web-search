"""
Scheduler Tests

Tests for HostGate, rate limiting, backoff, and crawl-delay.
"""

import time
from unittest.mock import MagicMock

from app.scheduler import HostGate, Scheduler, SchedulerConfig, MAX_BACKOFF


class TestHostGate:
    def test_defaults(self):
        gate = HostGate()
        assert gate.next_fetch_at == 0.0
        assert gate.inflight == 0
        assert gate.min_interval == 1.0
        assert gate.concurrency_limit == 2
        assert gate.fail_streak == 0

    def test_custom_values(self):
        gate = HostGate(min_interval=5.0, concurrency_limit=1, fail_streak=3)
        assert gate.min_interval == 5.0
        assert gate.concurrency_limit == 1
        assert gate.fail_streak == 3


class TestSchedulerRateLimiting:
    def _make_scheduler(self, **kwargs):
        url_store = MagicMock()
        url_store.pop_batch.return_value = []
        url_store.pending_count.return_value = 0
        config = SchedulerConfig(**kwargs)
        return Scheduler(url_store, config)

    def test_can_fetch_initially(self):
        s = self._make_scheduler()
        assert s._can_fetch("example.com", time.time()) is True

    def test_interval_blocks_fetch(self):
        s = self._make_scheduler(domain_min_interval=10.0)
        now = time.time()
        # Simulate a completed request that sets next_fetch_at
        s.record_start("example.com")
        s.record_complete("example.com", success=True)
        # Should be blocked for 10 seconds
        assert s._can_fetch("example.com", now + 1) is False
        assert s._can_fetch("example.com", now + 11) is True

    def test_concurrency_blocks_fetch(self):
        s = self._make_scheduler(domain_max_concurrent=2)
        now = time.time()
        s.record_start("example.com")
        s.record_start("example.com")
        # 2 inflight = at limit
        assert s._can_fetch("example.com", now + 100) is False
        # Complete one
        s.record_complete("example.com", success=True)
        assert s._can_fetch("example.com", now + 100) is True

    def test_record_start_increments_inflight(self):
        s = self._make_scheduler()
        s.record_start("example.com")
        gate = s._get_gate("example.com")
        assert gate.inflight == 1
        s.record_start("example.com")
        assert gate.inflight == 2

    def test_record_complete_decrements_inflight(self):
        s = self._make_scheduler()
        s.record_start("example.com")
        s.record_start("example.com")
        gate = s._get_gate("example.com")
        assert gate.inflight == 2
        s.record_complete("example.com")
        assert gate.inflight == 1

    def test_inflight_does_not_go_negative(self):
        s = self._make_scheduler()
        s.record_complete("example.com")
        gate = s._get_gate("example.com")
        assert gate.inflight == 0


class TestBackoff:
    def _make_scheduler(self, **kwargs):
        url_store = MagicMock()
        url_store.pop_batch.return_value = []
        url_store.pending_count.return_value = 0
        config = SchedulerConfig(**kwargs)
        return Scheduler(url_store, config)

    def test_fail_streak_increases_backoff(self):
        s = self._make_scheduler(domain_min_interval=1.0)
        gate = s._get_gate("example.com")

        # First failure: backoff = 1.0 * 2^1 = 2s
        s.record_start("example.com")
        s.record_complete("example.com", success=False)
        assert gate.fail_streak == 1
        # backoff = 1.0 * 2^1 = 2.0, next_fetch_at should be ~ now + 2.0
        assert gate.next_fetch_at > time.time() - 1  # sanity

        # Second failure: backoff = 1.0 * 2^2 = 4s
        s.record_start("example.com")
        s.record_complete("example.com", success=False)
        assert gate.fail_streak == 2

        # Third failure: backoff = 1.0 * 2^3 = 8s
        s.record_start("example.com")
        s.record_complete("example.com", success=False)
        assert gate.fail_streak == 3

    def test_success_resets_fail_streak(self):
        s = self._make_scheduler()
        gate = s._get_gate("example.com")

        # Build up fail streak
        s.record_start("example.com")
        s.record_complete("example.com", success=False)
        s.record_start("example.com")
        s.record_complete("example.com", success=False)
        assert gate.fail_streak == 2

        # Success resets
        s.record_start("example.com")
        s.record_complete("example.com", success=True)
        assert gate.fail_streak == 0

    def test_backoff_capped_at_max(self):
        s = self._make_scheduler(domain_min_interval=1.0)
        gate = s._get_gate("example.com")

        # Simulate many failures to exceed MAX_BACKOFF
        for _ in range(20):
            s.record_start("example.com")
            s.record_complete("example.com", success=False)

        # Backoff should be capped
        now = time.time()
        # next_fetch_at should not exceed now + MAX_BACKOFF + small margin
        assert gate.next_fetch_at <= now + MAX_BACKOFF + 1

    def test_backed_off_domains_in_stats(self):
        s = self._make_scheduler()
        s.record_start("example.com")
        s.record_complete("example.com", success=False)
        stats = s.stats()
        assert stats["backed_off_domains"] == 1

    def test_no_backed_off_after_success(self):
        s = self._make_scheduler()
        s.record_start("example.com")
        s.record_complete("example.com", success=True)
        stats = s.stats()
        assert stats["backed_off_domains"] == 0


class TestCrawlDelay:
    def _make_scheduler(self, **kwargs):
        url_store = MagicMock()
        url_store.pop_batch.return_value = []
        url_store.pending_count.return_value = 0
        config = SchedulerConfig(**kwargs)
        return Scheduler(url_store, config)

    def test_set_crawl_delay_updates_min_interval(self):
        s = self._make_scheduler(domain_min_interval=1.0)
        s.set_crawl_delay("example.com", 5.0)
        gate = s._get_gate("example.com")
        assert gate.min_interval == 5.0

    def test_set_crawl_delay_ignores_lower_value(self):
        s = self._make_scheduler(domain_min_interval=2.0)
        s.set_crawl_delay("example.com", 1.0)
        gate = s._get_gate("example.com")
        assert gate.min_interval == 2.0

    def test_crawl_delay_affects_interval_check(self):
        s = self._make_scheduler(domain_min_interval=1.0)
        s.set_crawl_delay("example.com", 10.0)
        now = time.time()

        # Complete a request to set next_fetch_at
        s.record_start("example.com")
        s.record_complete("example.com", success=True)

        gate = s._get_gate("example.com")
        # next_fetch_at should use min_interval=10.0
        assert gate.next_fetch_at >= now + 9.0  # small tolerance

    def test_crawl_delay_affects_backoff_base(self):
        s = self._make_scheduler(domain_min_interval=1.0)
        s.set_crawl_delay("example.com", 5.0)
        now = time.time()

        # Fail once: backoff = 5.0 * 2^1 = 10s
        s.record_start("example.com")
        s.record_complete("example.com", success=False)

        gate = s._get_gate("example.com")
        assert gate.next_fetch_at >= now + 9.0  # 10s with tolerance
