"""Tests for RetryPolicy and dedupe helpers."""

from app.services.dedupe import build_dedupe_key, hash_text
from app.services.retry_policy import RetryPolicy


class TestRetryPolicy:
    def test_delay_exponential_backoff(self):
        policy = RetryPolicy(base_seconds=5, max_seconds=1800)
        assert policy.delay_seconds(1) == 5
        assert policy.delay_seconds(2) == 10
        assert policy.delay_seconds(3) == 20

    def test_delay_capped_at_max(self):
        policy = RetryPolicy(base_seconds=5, max_seconds=30)
        assert policy.delay_seconds(10) == 30

    def test_is_exhausted(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.is_exhausted(2) is False
        assert policy.is_exhausted(3) is True
        assert policy.is_exhausted(4) is True

    def test_is_exhausted_zero(self):
        policy = RetryPolicy(max_retries=0)
        assert policy.is_exhausted(0) is True


class TestDedupe:
    def test_hash_text_deterministic(self):
        assert hash_text("hello") == hash_text("hello")

    def test_hash_text_different_inputs(self):
        assert hash_text("hello") != hash_text("world")

    def test_build_dedupe_key_deterministic(self):
        key1 = build_dedupe_key("url", "hash1", "hash2")
        key2 = build_dedupe_key("url", "hash1", "hash2")
        assert key1 == key2

    def test_build_dedupe_key_different_urls(self):
        key1 = build_dedupe_key("url1", "hash", "")
        key2 = build_dedupe_key("url2", "hash", "")
        assert key1 != key2

    def test_build_dedupe_key_different_content(self):
        key1 = build_dedupe_key("url", "hash1", "")
        key2 = build_dedupe_key("url", "hash2", "")
        assert key1 != key2
