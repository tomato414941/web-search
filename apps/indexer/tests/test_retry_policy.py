"""Tests for RetryPolicy."""

from web_search_core.retry import RetryPolicy


class TestRetryPolicy:
    def test_delay_exponential_backoff(self):
        policy = RetryPolicy(base_delay=5, max_delay=1800)
        assert policy.delay_seconds(1) == 5
        assert policy.delay_seconds(2) == 10
        assert policy.delay_seconds(3) == 20

    def test_delay_capped_at_max(self):
        policy = RetryPolicy(base_delay=5, max_delay=30)
        assert policy.delay_seconds(10) == 30

    def test_is_exhausted(self):
        policy = RetryPolicy(max_attempts=3)
        assert policy.is_exhausted(2) is False
        assert policy.is_exhausted(3) is True
        assert policy.is_exhausted(4) is True

    def test_is_exhausted_zero(self):
        policy = RetryPolicy(max_attempts=0)
        assert policy.is_exhausted(0) is True
