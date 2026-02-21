"""Tests for BM25 stats cache TTL behavior."""

import time
from unittest.mock import MagicMock

from shared.search.scoring import BM25Scorer


def test_stats_cache_respects_ttl():
    """Stats cache should be invalidated after STATS_CACHE_TTL seconds."""
    scorer = BM25Scorer(db_path=":memory:")

    call_count = 0

    def fake_fetchall():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [("total_docs", 100.0), ("avg_doc_length", 50.0)]
        return [("total_docs", 200.0), ("avg_doc_length", 60.0)]

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall = fake_fetchall
    mock_conn.cursor.return_value = mock_cursor

    # First call: populate cache
    total, avg = scorer._get_global_stats(mock_conn)
    assert total == 100.0
    assert avg == 50.0
    assert call_count == 1

    # Second call within TTL: cached
    total, avg = scorer._get_global_stats(mock_conn)
    assert total == 100.0
    assert avg == 50.0
    assert call_count == 1

    # Simulate TTL expiration
    scorer._stats_cache_loaded_at = time.monotonic() - scorer.STATS_CACHE_TTL - 1

    # Third call after TTL: re-fetch
    total, avg = scorer._get_global_stats(mock_conn)
    assert total == 200.0
    assert avg == 60.0
    assert call_count == 2


def test_clear_cache_resets_stats_timestamp():
    """clear_cache should reset _stats_cache_loaded_at."""
    scorer = BM25Scorer(db_path=":memory:")
    scorer._stats_cache_loaded_at = 12345.0
    scorer._stats_cache["total_docs"] = 100.0

    scorer.clear_cache()

    assert scorer._stats_cache_loaded_at == 0.0
    assert len(scorer._stats_cache) == 0
