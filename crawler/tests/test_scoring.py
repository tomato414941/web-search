"""Tests for URL scoring domain logic."""

import pytest

from app.domain.scoring import (
    DEFAULT_BASE,
    MANUAL_CRAWL_BOOST,
    MAX_INHERITED,
    SEED_BOOST,
    TRANCO_BOOST,
    _domain_base,
    _base_score,
    _depth_factor,
    _diversity_factor,
    _path_factor,
    calculate_url_score,
    seed_score,
)


# ---- _domain_base ----


class TestDomainBase:
    def test_none_returns_default(self):
        assert _domain_base(None) == DEFAULT_BASE

    def test_zero_returns_near_zero(self):
        # rank=0.0 is the lowest-ranked domain, not unknown
        # log10(0*1000+1)/3*100 = 0.0
        assert _domain_base(0.0) == pytest.approx(0.0, abs=0.1)

    def test_high_rank(self):
        # twitter-class domain (rank ~1.0)
        score = _domain_base(1.0)
        assert score == 100.0

    def test_mid_rank(self):
        # github-class domain (rank ~0.39)
        score = _domain_base(0.39)
        assert 80.0 < score < 95.0

    def test_low_rank(self):
        # average domain (rank ~0.003)
        score = _domain_base(0.003)
        assert 10.0 < score < 30.0

    def test_capped_at_100(self):
        assert _domain_base(10.0) == 100.0

    def test_negative_returns_default(self):
        assert _domain_base(-0.5) == DEFAULT_BASE


# ---- _base_score ----


class TestBaseScore:
    def test_domain_rank_preferred(self, monkeypatch):
        # When domain_rank is available and cache is populated
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {"example.com": 0.5})
        score = _base_score(0.5, parent_score=80.0)
        assert score == _domain_base(0.5)

    def test_parent_inheritance_capped(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {})
        # parent=100 * 0.8 = 80 → capped at MAX_INHERITED=40
        score = _base_score(None, parent_score=100.0)
        assert score == MAX_INHERITED

    def test_parent_inheritance_floor(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {})
        # parent=5 * 0.8 = 4 → floor at DEFAULT_BASE=15
        score = _base_score(None, parent_score=5.0)
        assert score == DEFAULT_BASE

    def test_parent_inheritance_normal(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {})
        # parent=30 * 0.8 = 24 → between DEFAULT_BASE and MAX_INHERITED
        score = _base_score(None, parent_score=30.0)
        assert score == pytest.approx(24.0)


# ---- _diversity_factor ----


class TestDiversityFactor:
    def test_zero_visits(self):
        assert _diversity_factor(0) == 1.0

    def test_negative_visits(self):
        assert _diversity_factor(-1) == 1.0

    def test_ten_visits(self):
        result = _diversity_factor(10)
        assert 0.85 < result < 0.95

    def test_thousand_visits(self):
        result = _diversity_factor(1000)
        assert 0.65 < result < 0.75

    def test_floor(self):
        result = _diversity_factor(10_000_000)
        assert result == pytest.approx(0.6, abs=0.01)


# ---- _depth_factor ----


class TestDepthFactor:
    def test_root(self):
        assert _depth_factor("https://example.com/") == pytest.approx(1.0)

    def test_depth_1(self):
        # /page has 1 slash → depth=0 → factor=1.0
        assert _depth_factor("https://example.com/page") == pytest.approx(1.0)

    def test_depth_2(self):
        # /a/b has 2 slashes → depth=1 → factor=0.9
        assert _depth_factor("https://example.com/a/b") == pytest.approx(0.9)

    def test_depth_3(self):
        # /a/b/c has 3 slashes → depth=2 → 0.9^2
        f = _depth_factor("https://example.com/a/b/c")
        assert f == pytest.approx(0.9**2)

    def test_floor(self):
        deep = "https://example.com" + "/a" * 20
        assert _depth_factor(deep) == pytest.approx(0.5)


# ---- _path_factor ----


class TestPathFactor:
    def test_neutral(self):
        assert _path_factor("https://example.com/page") == 1.0

    def test_boost_wiki(self):
        assert _path_factor("https://example.com/wiki/Python") == 1.2

    def test_boost_docs(self):
        assert _path_factor("https://example.com/docs/api") == 1.2

    def test_boost_index(self):
        assert _path_factor("https://example.com/products/index") == 1.2

    def test_penalty_login(self):
        assert _path_factor("https://example.com/login") == 0.5

    def test_penalty_tags(self):
        assert _path_factor("https://example.com/tags/python") == 0.5

    def test_penalty_tag_singular(self):
        assert _path_factor("https://example.com/tag/python") == 0.5

    def test_no_false_positive_staging(self):
        # "staging" should NOT match "tag"
        assert _path_factor("https://example.com/staging/app") == 1.0

    def test_no_false_positive_category_in_word(self):
        # Ensure word boundary: "subcategory" should not match "category"
        # Actually /subcategory contains /category so this is a valid match
        # The regex checks for preceding boundary char
        result = _path_factor("https://example.com/subcategory/items")
        # subcategory doesn't start with boundary before "category"
        assert result == 1.0

    def test_no_false_positive_login_in_word(self):
        # "blogin" should not match "login"
        assert _path_factor("https://example.com/blogin/page") == 1.0

    def test_penalty_admin(self):
        assert _path_factor("https://example.com/admin/settings") == 0.5

    def test_penalty_checkout(self):
        assert _path_factor("https://example.com/checkout") == 0.5


# ---- calculate_url_score ----


class TestCalculateUrlScore:
    def test_score_in_range(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {"example.com": 0.5})
        score = calculate_url_score(
            "https://example.com/page",
            parent_score=50,
            domain_visits=10,
            domain_pagerank=0.5,
        )
        assert 0 <= score <= 100

    def test_high_rank_high_score(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {"twitter.com": 1.0})
        score = calculate_url_score(
            "https://twitter.com/explore",
            parent_score=0,
            domain_visits=0,
            domain_pagerank=1.0,
        )
        # High rank + root-ish depth + no visits → high score
        assert score > 80

    def test_unknown_domain_low_parent(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {})
        score = calculate_url_score(
            "https://unknown.example.com/a/b/c/login",
            parent_score=20,
            domain_visits=0,
            domain_pagerank=None,
        )
        # Low parent + deep path + login penalty → low score
        assert score < 15

    def test_all_scores_non_negative(self, monkeypatch):
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {})
        score = calculate_url_score(
            "https://example.com/a/b/c/d/e/f/g/h/i/login",
            parent_score=0,
            domain_visits=999999,
            domain_pagerank=None,
        )
        assert score >= 0

    def test_boost_path_capped_at_100(self, monkeypatch):
        """path_factor=1.2 should not push score over 100."""
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {"twitter.com": 1.0})
        score = calculate_url_score(
            "https://twitter.com/wiki",
            parent_score=0,
            domain_visits=0,
            domain_pagerank=1.0,
        )
        assert score <= 100.0

    def test_domain_rank_used_when_cache_empty(self, monkeypatch):
        """domain_pagerank should be used even if cache dict is empty."""
        import app.domain.scoring as scoring_mod

        monkeypatch.setattr(scoring_mod, "_domain_rank_cache", {})
        score = calculate_url_score(
            "https://example.com/page",
            parent_score=10,
            domain_visits=0,
            domain_pagerank=0.5,
        )
        # Should use domain_base(0.5) ≈ 89, not parent inheritance
        assert score > 50


# ---- seed_score ----


class TestSeedScore:
    def test_unknown_domain_seed(self):
        score = seed_score(domain_pagerank=None, boost=SEED_BOOST)
        assert score == DEFAULT_BASE + SEED_BOOST

    def test_high_rank_seed_capped(self):
        score = seed_score(domain_pagerank=1.0, boost=SEED_BOOST)
        assert score == 100.0

    def test_manual_crawl_boost(self):
        score = seed_score(domain_pagerank=None, boost=MANUAL_CRAWL_BOOST)
        assert score == DEFAULT_BASE + MANUAL_CRAWL_BOOST

    def test_tranco_boost(self):
        score = seed_score(domain_pagerank=None, boost=TRANCO_BOOST)
        assert score == DEFAULT_BASE + TRANCO_BOOST

    def test_mid_rank_seed(self):
        score = seed_score(domain_pagerank=0.39, boost=SEED_BOOST)
        assert score == min(100.0, _domain_base(0.39) + SEED_BOOST)
        assert score <= 100.0
