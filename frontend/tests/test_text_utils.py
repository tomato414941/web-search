"""Test text processing utilities."""

from frontend.services.text_utils import highlight_snippet


class TestHighlightSnippet:
    """Test snippet highlighting."""

    def test_basic_highlighting(self):
        """Should highlight matching terms."""
        text = "This is a test document with some test content."
        result = highlight_snippet(text, ["test"])
        assert "<mark>test</mark>" in result

    def test_multiple_terms(self):
        """Should highlight multiple terms."""
        text = "Python is great for testing applications."
        result = highlight_snippet(text, ["Python", "testing"])
        assert (
            "<mark>Python</mark>" in result or "<mark>python</mark>" in result.lower()
        )
        assert "<mark>testing</mark>" in result or "<mark>Testing</mark>" in result

    def test_case_insensitive(self):
        """Should highlight case-insensitively."""
        text = "Testing is important for TEST quality."
        result = highlight_snippet(text, ["test"])
        # Should match both "Testing" and "TEST"
        assert "<mark>" in result
        assert result.count("<mark>") >= 2

    def test_empty_terms(self):
        """Should return truncated text with no highlighting for empty terms."""
        text = "This is a long document that needs truncation."
        result = highlight_snippet(text, [])
        assert "<mark>" not in result
        assert len(result) <= 153  # window_size + "..."

    def test_empty_text(self):
        """Should return empty string for empty text."""
        result = highlight_snippet("", ["test"])
        assert result == ""

    def test_no_matches(self):
        """Should return snippet without highlighting when no matches."""
        text = "This document has no matching terms."
        result = highlight_snippet(text, ["notfound"])
        assert "<mark>" not in result
        assert "..." in result

    def test_window_size(self):
        """Should respect window size parameter."""
        text = "a" * 500  # Long text
        result = highlight_snippet(text, ["test"], window_size=50)
        # Should be approximately window_size + ellipsis
        assert len(result) < 100

    def test_special_characters(self):
        """Should handle special regex characters."""
        text = "Price is $100.99 for this item."
        result = highlight_snippet(text, ["$100"])
        # Should not crash due to $ being special in regex
        assert result is not None

    def test_ellipsis_prefix(self):
        """Should add prefix ellipsis when not starting at beginning."""
        text = "a" * 200 + " important " + "b" * 200
        result = highlight_snippet(text, ["important"], window_size=50)
        assert result.startswith("...")

    def test_ellipsis_suffix(self):
        """Should add suffix ellipsis when not ending at end."""
        text = "important word " + "a" * 200
        result = highlight_snippet(text, ["important"], window_size=50)
        assert result.endswith("...")
