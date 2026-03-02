"""Tests for domain diversity filtering."""

import os

os.environ.setdefault("ENVIRONMENT", "test")

from shared.search_kernel.diversify import diversify_hits
from shared.search_kernel.searcher import SearchHit


def _hit(url: str, score: float) -> SearchHit:
    return SearchHit(url=url, title="", content="", score=score)


class TestDiversifyHits:
    def test_empty(self):
        assert diversify_hits([], limit=10) == []

    def test_all_different_domains(self):
        hits = [
            _hit("https://a.com/1", 5.0),
            _hit("https://b.com/1", 4.0),
            _hit("https://c.com/1", 3.0),
        ]
        result = diversify_hits(hits, limit=10, max_per_domain=3)
        assert len(result) == 3

    def test_single_domain_capped(self):
        hits = [_hit(f"https://a.com/{i}", 10.0 - i) for i in range(10)]
        result = diversify_hits(hits, limit=10, max_per_domain=3)
        assert len(result) == 3
        assert all("a.com" in h.url for h in result)

    def test_mixed_domains_preserves_order(self):
        hits = [
            _hit("https://a.com/1", 10.0),
            _hit("https://a.com/2", 9.0),
            _hit("https://a.com/3", 8.0),
            _hit("https://a.com/4", 7.0),  # should be dropped
            _hit("https://b.com/1", 6.0),
            _hit("https://b.com/2", 5.0),
            _hit("https://c.com/1", 4.0),
        ]
        result = diversify_hits(hits, limit=10, max_per_domain=3)
        assert len(result) == 6
        urls = [h.url for h in result]
        assert "https://a.com/4" not in urls
        # Score order preserved
        scores = [h.score for h in result]
        assert scores == sorted(scores, reverse=True)

    def test_limit_respected(self):
        hits = [
            _hit(f"https://d{i}.com/1", 10.0 - i) for i in range(20)
        ]
        result = diversify_hits(hits, limit=5, max_per_domain=3)
        assert len(result) == 5

    def test_max_per_domain_one(self):
        hits = [
            _hit("https://a.com/1", 10.0),
            _hit("https://a.com/2", 9.0),
            _hit("https://b.com/1", 8.0),
            _hit("https://b.com/2", 7.0),
        ]
        result = diversify_hits(hits, limit=10, max_per_domain=1)
        assert len(result) == 2
        urls = [h.url for h in result]
        assert urls == ["https://a.com/1", "https://b.com/1"]

    def test_malformed_url(self):
        hits = [
            _hit("not-a-url", 5.0),
            _hit("https://a.com/1", 4.0),
        ]
        result = diversify_hits(hits, limit=10, max_per_domain=3)
        assert len(result) == 2
