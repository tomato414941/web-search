"""
Parser Utility Tests

Tests for HTML parsing and link extraction utilities.
"""

from app.utils import parser as parser_module
from app.utils.parser import parse_page
from shared.core.utils import normalize_url


# ==========================================
# Tests for normalize_url
# ==========================================


def test_normalize_url_basic():
    base = "http://example.com/page1"
    link = "page2.html"
    expected = "http://example.com/page2.html"
    assert normalize_url(base, link) == expected


def test_normalize_url_absolute():
    base = "http://example.com/page1"
    link = "http://other.com/foo"
    assert normalize_url(base, link) == "http://other.com/foo"


def test_normalize_url_remove_fragment():
    base = "http://example.com"
    link = "http://example.com/page#section"
    assert normalize_url(base, link) == "http://example.com/page"


def test_normalize_url_remove_tracking_params():
    base = "http://example.com"
    link = "http://example.com/item?id=123&utm_source=twitter&fbclid=xyz"
    # Should keep id=123 but remove utm_source and fbclid
    normalized = normalize_url(base, link)
    assert "id=123" in normalized
    assert "utm_source" not in normalized
    assert "fbclid" not in normalized


def test_normalize_url_lowercase_host():
    base = "http://EXAMPLE.COM"
    link = "/foo"
    expected = "http://example.com/foo"
    assert normalize_url(base, link) == expected


def test_normalize_url_invalid_scheme():
    base = "http://example.com"
    link = "mailto:user@example.com"
    assert normalize_url(base, link) is None

    link = "javascript:alert(1)"
    assert normalize_url(base, link) is None


def test_normalize_url_too_long():
    base = "http://example.com"
    link = "/" + ("a" * 3000)
    assert normalize_url(base, link) is None


# ==========================================
# Tests for parse_page: content extraction
# ==========================================


def test_parse_page_extraction():
    html = """
    <html>
    <head><title>  My Title  </title></head>
    <body>
        <h1>Header</h1>
        <p>Paragraph text.</p>
        <script>console.log('ignore');</script>
        <style>body { color: red; }</style>
    </body>
    </html>
    """
    doc = parse_page(html, "http://example.com")
    assert doc.title == "My Title"
    assert "Header" in doc.content
    assert "Paragraph text." in doc.content
    assert "console.log" not in doc.content
    assert "color: red" not in doc.content


def test_parse_page_no_title():
    html = "<body><p>Hello</p></body>"
    doc = parse_page(html, "http://example.com")
    assert doc.title == ""
    assert "Hello" in doc.content


def test_parse_page_empty():
    html = "<html></html>"
    doc = parse_page(html, "http://example.com")
    assert doc.title == ""
    assert doc.content == ""


def test_parse_page_strips_nul_characters():
    html = "<html><head><title>A\x00B</title></head><body>hello\x00world</body></html>"
    doc = parse_page(html, "http://example.com")
    assert "\x00" not in doc.title
    assert "\x00" not in doc.content
    assert doc.title == "A B"
    assert "hello world" in doc.content


# ==========================================
# Tests for trafilatura integration
# ==========================================


def test_parse_page_strips_boilerplate():
    """trafilatura should extract main content, ignoring nav/footer."""
    html = """
    <html>
    <head><title>Article Page</title></head>
    <body>
        <nav><a href="/">Home</a> | <a href="/about">About</a> | <a href="/contact">Contact</a></nav>
        <main>
            <article>
                <h1>Main Article Title</h1>
                <p>This is the main article content that should be extracted by trafilatura.
                It contains multiple sentences of useful information for the reader.
                The content is substantial enough for trafilatura to recognize it as main text.</p>
                <p>Another paragraph with more detailed information about the topic at hand.
                This helps ensure the article has enough content density to be recognized.</p>
            </article>
        </main>
        <footer>Copyright 2025 Example Corp. All rights reserved.
            <a href="/privacy">Privacy Policy</a> | <a href="/terms">Terms of Service</a>
        </footer>
    </body>
    </html>
    """
    doc = parse_page(html, "http://example.com")
    assert doc.title == "Article Page"
    assert "Main Article Title" in doc.content
    assert "main article content" in doc.content


def test_parse_page_fallback_on_minimal_html():
    """trafilatura returns None for minimal HTML; BS4 fallback should work."""
    html = "<p>Just a short paragraph</p>"
    doc = parse_page(html, "http://example.com")
    assert "Just a short paragraph" in doc.content


def test_parse_page_enriches_sparse_homepage_content(monkeypatch):
    html = """
    <html>
    <head>
        <title>GitHub</title>
        <meta name="description" content="The platform for developers to build software together.">
    </head>
    <body>
        <h1>Build and ship software</h1>
        <h2>Code</h2>
        <h2>Collaborate</h2>
    </body>
    </html>
    """

    monkeypatch.setattr(
        parser_module.trafilatura, "extract", lambda *args, **kwargs: "GitHub"
    )

    doc = parse_page(html, "https://github.com/")

    assert "The platform for developers to build software together." in doc.content
    assert "Build and ship software" in doc.content
    assert "Collaborate" in doc.content


def test_parse_page_does_not_enrich_sparse_non_homepage(monkeypatch):
    html = """
    <html>
    <head>
        <title>GitHub Docs</title>
        <meta name="description" content="Developer documentation for GitHub.">
    </head>
    <body>
        <h1>GitHub Docs</h1>
        <h2>Actions</h2>
    </body>
    </html>
    """

    monkeypatch.setattr(
        parser_module.trafilatura, "extract", lambda *args, **kwargs: "GitHub Docs"
    )

    doc = parse_page(html, "https://docs.github.com/en")

    assert doc.content == "GitHub Docs"


def test_parse_page_preserves_table_content():
    """Tables should be included (include_tables=True)."""
    html = """
    <html>
    <head><title>Comparison</title></head>
    <body>
        <article>
            <h1>Framework Comparison</h1>
            <p>Here is a detailed comparison of popular Python web frameworks
            that developers frequently use for building modern applications.</p>
            <table>
                <tr><th>Framework</th><th>Speed</th></tr>
                <tr><td>FastAPI</td><td>Fast</td></tr>
                <tr><td>Django</td><td>Moderate</td></tr>
            </table>
            <p>FastAPI is known for its high performance while Django provides
            a more comprehensive set of built-in features for rapid development.</p>
        </article>
    </body>
    </html>
    """
    doc = parse_page(html, "http://example.com")
    assert "FastAPI" in doc.content
    assert "Django" in doc.content


# ==========================================
# Tests for parse_page: link extraction
# ==========================================


def test_parse_page_extract_links():
    base = "http://example.com"
    html = """
    <a href="/one">One</a>
    <a href="http://other.com">Other</a>
    <a href="#skip">Skip</a>
    """
    doc = parse_page(html, base)
    assert "http://example.com/one" in doc.outlinks
    assert "http://other.com" in doc.outlinks


def test_parse_page_extract_links_limit():
    base = "http://example.com"
    html = "".join([f'<a href="/page{i}">Link {i}</a>' for i in range(20)])
    doc = parse_page(html, base, max_outlinks=10)
    assert len(doc.outlinks) == 10


def test_parse_page_extract_links_relative():
    base = "http://example.com/dir/"
    html = '<a href="page.html">Link</a>'
    doc = parse_page(html, base)
    assert "http://example.com/dir/page.html" in doc.outlinks


def test_parse_page_extract_links_ignore_invalid():
    base = "http://example.com"
    html = """
    <a href="mailto:test@example.com">Email</a>
    <a href="javascript:void(0)">JS</a>
    <a href="http://valid.com">Valid</a>
    """
    doc = parse_page(html, base)
    assert "http://valid.com" in doc.outlinks
    assert not any("mailto" in link for link in doc.outlinks)
    assert not any("javascript" in link for link in doc.outlinks)
