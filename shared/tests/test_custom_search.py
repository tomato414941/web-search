"""
Tests for snippet generation and query parsing.

BM25 search tests were removed in Phase 4 (OpenSearch migration).
"""

from shared.search_kernel.searcher import parse_query


class TestSnippetGeneration:
    """Tests for snippet generation."""

    def test_basic_snippet(self):
        """Test basic snippet generation with highlighting."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Python is a programming language. Python is popular."
        snippet = generate_snippet(text, ["Python"])

        assert "Python" in snippet.plain_text
        assert "<mark>Python</mark>" in snippet.text

    def test_snippet_context_window(self):
        """Test that snippet shows context around match."""
        from shared.search_kernel.snippet import generate_snippet

        # Long text with keyword in the middle
        text = "A" * 100 + " Python " + "B" * 100
        snippet = generate_snippet(text, ["Python"], window_size=50)

        # Should contain Python and be approximately window_size
        assert "Python" in snippet.plain_text
        assert len(snippet.plain_text) < 150  # Roughly window_size + ellipsis

    def test_snippet_ellipsis(self):
        """Test that ellipsis is added when text is truncated."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Start " + "X" * 200 + " Python " + "Y" * 200 + " End"
        snippet = generate_snippet(text, ["Python"], window_size=50)

        # Should have ellipsis at start and end
        assert snippet.plain_text.startswith("...")
        assert snippet.plain_text.endswith("...")

    def test_snippet_no_highlight(self):
        """Test snippet without HTML highlighting."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Python is great"
        snippet = generate_snippet(text, ["Python"], highlight=False)

        assert "<mark>" not in snippet.text
        assert snippet.text == snippet.plain_text

    def test_snippet_empty_terms(self):
        """Test snippet with no search terms."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Some text content here"
        snippet = generate_snippet(text, [], window_size=10)

        assert snippet.text == "Some text ..."

    def test_snippet_no_match(self):
        """Test snippet when terms don't match."""
        from shared.search_kernel.snippet import generate_snippet

        text = "This text has no matches"
        snippet = generate_snippet(text, ["Python"])

        # Should return beginning of text
        assert snippet.text.startswith("This text")

    def test_html_escape_in_snippet(self):
        """Test that HTML entities in content are escaped."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Use <div> tags and & symbols in Python code"
        snippet = generate_snippet(text, ["Python"])

        assert "&lt;div&gt;" in snippet.text
        assert "&amp;" in snippet.text
        assert "<mark>Python</mark>" in snippet.text
        # Plain text should NOT be escaped
        assert "<div>" in snippet.plain_text

    def test_xss_prevention_in_snippet(self):
        """Test that script tags in content are neutralized."""
        from shared.search_kernel.snippet import generate_snippet

        text = '<script>alert("xss")</script> Python is safe'
        snippet = generate_snippet(text, ["Python"])

        assert "<script>" not in snippet.text
        assert "&lt;script&gt;" in snippet.text
        assert "<mark>Python</mark>" in snippet.text

    def test_html_escape_in_matched_term(self):
        """Test that matched terms with special chars are escaped."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Search for A&B in the document"
        snippet = generate_snippet(text, ["A&B"])

        assert "<mark>A&amp;B</mark>" in snippet.text
        assert "A&B" in snippet.plain_text

    def test_best_window_multi_term(self):
        """Test that best-window picks the region with most distinct terms."""
        from shared.search_kernel.snippet import generate_snippet

        # Python appears early, but Python+JavaScript cluster later
        text = (
            "Python is a language. "
            + "X" * 300
            + " Python and JavaScript are both popular."
        )
        snippet = generate_snippet(text, ["Python", "JavaScript"], window_size=80)

        # Best window should contain both terms
        assert "Python" in snippet.plain_text
        assert "JavaScript" in snippet.plain_text

    def test_ja_sentence_boundary(self):
        """Test that snippet snaps to Japanese sentence boundary."""
        from shared.search_kernel.snippet import generate_snippet

        text = (
            "これは前置きです。Pythonは素晴らしい言語です。他の話題が続きます。"
            + "X" * 300
        )
        snippet = generate_snippet(text, ["Python"], window_size=40)

        # Should start at or near a JA sentence boundary
        plain = snippet.plain_text.lstrip(".")
        assert not plain.startswith("きです"), "Should not cut mid-sentence"

    def test_default_window_size_200(self):
        """Test that default window size is 200."""
        from shared.search_kernel.snippet import generate_snippet

        text = "Python " + "word " * 100
        snippet = generate_snippet(text, ["Python"])

        # Plain text (minus ellipsis) should be around 200 chars
        clean = snippet.plain_text.strip(".")
        assert len(clean) >= 100


class TestParseQuery:
    """Test query parser for operators."""

    def test_no_operators(self):
        parsed = parse_query("Python tutorial")
        assert parsed.text == "Python tutorial"
        assert parsed.site_filter is None

    def test_site_operator(self):
        parsed = parse_query("Python site:github.com")
        assert parsed.text == "Python"
        assert parsed.site_filter == "github.com"

    def test_site_operator_at_start(self):
        parsed = parse_query("site:example.com Python")
        assert parsed.text == "Python"
        assert parsed.site_filter == "example.com"

    def test_site_operator_case_insensitive(self):
        parsed = parse_query("Python SITE:GitHub.COM")
        assert parsed.site_filter == "github.com"

    def test_site_operator_only(self):
        parsed = parse_query("site:example.com")
        assert parsed.text == ""
        assert parsed.site_filter == "example.com"
