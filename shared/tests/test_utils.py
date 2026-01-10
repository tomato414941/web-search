"""Test utility functions."""

from shared.core.utils import normalize_url


class TestNormalizeURL:
    """Test URL normalization."""

    def test_absolute_url(self):
        """Should handle absolute URLs."""
        result = normalize_url("http://example.com", "https://other.com/page")
        assert result == "https://other.com/page"

    def test_relative_url(self):
        """Should resolve relative URLs."""
        result = normalize_url("http://example.com/page", "/other")
        assert result == "http://example.com/other"

    def test_fragment_removal(self):
        """Should remove URL fragments."""
        result = normalize_url("http://example.com", "http://example.com/page#section")
        assert result == "http://example.com/page"

    def test_tracking_params_removal(self):
        """Should remove tracking parameters."""
        url = "http://example.com/page?utm_source=test&utm_medium=email&id=123"
        result = normalize_url("http://example.com", url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=123" in result  # Keep non-tracking params

    def test_lowercase_scheme_and_host(self):
        """Should lowercase scheme and hostname."""
        result = normalize_url("http://example.com", "HTTP://EXAMPLE.COM/Page")
        assert result.startswith("http://example.com")

    def test_none_link(self):
        """Should return None for None input."""
        result = normalize_url("http://example.com", None)
        assert result is None

    def test_empty_link(self):
        """Should return None for empty string."""
        result = normalize_url("http://example.com", "")
        assert result is None

    def test_javascript_protocol(self):
        """Should reject javascript: URLs."""
        result = normalize_url("http://example.com", "javascript:alert('xss')")
        assert result is None

    def test_mailto_protocol(self):
        """Should reject mailto: URLs."""
        result = normalize_url("http://example.com", "mailto:test@example.com")
        assert result is None

