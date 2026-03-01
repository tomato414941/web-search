"""Tests for stale link cleanup and outlinks dedupe."""

from app.services.dedupe import build_dedupe_key


class TestOutlinksDedupe:
    def test_different_outlinks_produce_different_dedupe_keys(self):
        """Same URL + content but different outlinks should not deduplicate."""
        key1 = build_dedupe_key("http://a.com", "abc123", "hash1")
        key2 = build_dedupe_key("http://a.com", "abc123", "hash2")
        assert key1 != key2

    def test_same_outlinks_produce_same_dedupe_key(self):
        """Same URL + content + outlinks should deduplicate."""
        key1 = build_dedupe_key("http://a.com", "abc123", "hash1")
        key2 = build_dedupe_key("http://a.com", "abc123", "hash1")
        assert key1 == key2

    def test_empty_outlinks_hash_backward_compatible(self):
        """Empty outlinks hash should produce a valid key."""
        key = build_dedupe_key("http://a.com", "abc123", "")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex digest
