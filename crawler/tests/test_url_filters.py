"""Tests for URL pattern filters."""

import tempfile
from pathlib import Path

from app.core.url_filters import UrlFilter, load_url_filters


def _make_filter(extensions=(), contains=()):
    return UrlFilter(frozenset(extensions), tuple(contains))


class TestUrlFilter:
    def test_extension_match(self):
        f = _make_filter(extensions=[".jpg", ".png"])
        assert f.is_filtered("https://example.com/photo.jpg")
        assert f.is_filtered("https://example.com/photo.PNG")
        assert not f.is_filtered("https://example.com/page.html")

    def test_extension_with_query_string(self):
        f = _make_filter(extensions=[".jpg"])
        assert f.is_filtered("https://example.com/photo.jpg?w=100")
        assert not f.is_filtered("https://example.com/page?file=photo.jpg")

    def test_contains_match(self):
        f = _make_filter(contains=["/login", "/signup"])
        assert f.is_filtered("https://example.com/login")
        assert f.is_filtered("https://example.com/user/signup?ref=1")
        assert not f.is_filtered("https://example.com/article")

    def test_contains_case_insensitive(self):
        f = _make_filter(contains=["/login"])
        assert f.is_filtered("https://example.com/Login")

    def test_no_filters(self):
        f = _make_filter()
        assert not f.is_filtered("https://example.com/anything")

    def test_combined(self):
        f = _make_filter(extensions=[".pdf"], contains=["/wp-content/"])
        assert f.is_filtered("https://example.com/doc.pdf")
        assert f.is_filtered("https://example.com/wp-content/uploads/img.html")
        assert not f.is_filtered("https://example.com/article")


class TestLoadUrlFilters:
    def test_load_valid_yaml(self):
        content = """
- pattern: ".jpg"
  match_type: extension
  reason: image
- pattern: "/login"
  match_type: contains
  reason: auth
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(content)
            f.flush()
            filt = load_url_filters(f.name)

        assert filt.is_filtered("https://example.com/photo.jpg")
        assert filt.is_filtered("https://example.com/login")
        assert not filt.is_filtered("https://example.com/article")

    def test_load_missing_file(self):
        filt = load_url_filters("/nonexistent/path.yml")
        assert not filt.is_filtered("https://example.com/photo.jpg")

    def test_load_production_file(self):
        prod_path = Path(__file__).parent.parent / "data" / "url_filters.yml"
        if prod_path.exists():
            filt = load_url_filters(prod_path)
            assert filt.is_filtered("https://example.com/photo.jpg")
            assert filt.is_filtered("https://example.com/login")
            assert filt.is_filtered("https://example.com/doc.pdf")
            assert not filt.is_filtered("https://example.com/article")
