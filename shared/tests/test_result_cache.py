"""Tests for search result caching in SearchEngine."""

import time
from unittest.mock import patch

from shared.search.searcher import SearchEngine, SearchResult


def _make_engine():
    """Create a SearchEngine with mocked DB."""
    return SearchEngine(db_path=":memory:")


class TestResultCache:
    def test_cache_hit_within_ttl(self):
        """Same query within TTL should return cached result."""
        engine = _make_engine()

        fake_result = SearchResult(
            query="test", total=5, hits=[], page=1, per_page=10, last_page=1
        )
        now = time.monotonic()
        engine._result_cache["test:10:1"] = (now, fake_result)

        result = engine.search("test", limit=10, page=1)
        assert result is fake_result

    def test_cache_miss_after_ttl(self):
        """Query after TTL expiration should not return cached result."""
        engine = _make_engine()

        fake_result = SearchResult(
            query="test", total=5, hits=[], page=1, per_page=10, last_page=1
        )
        expired_time = time.monotonic() - engine.RESULT_CACHE_TTL - 1
        engine._result_cache["test:10:1"] = (expired_time, fake_result)

        # Mock _find_candidates to return empty (no real DB)
        with patch.object(engine, "_find_candidates", return_value=set()):
            result = engine.search("test", limit=10, page=1)
        assert result is not fake_result
        assert result.total == 0

    def test_different_params_different_cache_keys(self):
        """Different limit/page should use different cache keys."""
        engine = _make_engine()

        result_p1 = SearchResult(
            query="test", total=5, hits=[], page=1, per_page=10, last_page=1
        )
        result_p2 = SearchResult(
            query="test", total=5, hits=[], page=2, per_page=10, last_page=1
        )
        now = time.monotonic()
        engine._result_cache["test:10:1"] = (now, result_p1)
        engine._result_cache["test:10:2"] = (now, result_p2)

        assert engine.search("test", limit=10, page=1) is result_p1
        assert engine.search("test", limit=10, page=2) is result_p2

    def test_clear_result_cache(self):
        """clear_result_cache should empty the cache."""
        engine = _make_engine()
        now = time.monotonic()
        fake_result = SearchResult(
            query="test", total=0, hits=[], page=1, per_page=10, last_page=1
        )
        engine._result_cache["test:10:1"] = (now, fake_result)

        engine.clear_result_cache()
        assert len(engine._result_cache) == 0
