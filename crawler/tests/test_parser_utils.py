"""
Parser Utility Tests

Tests for HTML parsing and link extraction utilities.
"""

from app.utils.parser import html_to_doc, extract_links
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
# Tests for html_to_doc
# ==========================================


def test_html_to_doc_extraction():
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
    title, text = html_to_doc(html)
    assert title == "My Title"
    assert "Header" in text
    assert "Paragraph text." in text
    # Confirm scripts/styles are removed
    assert "console.log" not in text
    assert "color: red" not in text


def test_html_to_doc_no_title():
    html = "<body><p>Hello</p></body>"
    title, text = html_to_doc(html)
    assert title == ""
    assert "Hello" in text


def test_html_to_doc_empty():
    html = "<html></html>"
    title, text = html_to_doc(html)
    assert title == ""
    assert text == ""


def test_html_to_doc_strips_nul_characters():
    html = "<html><head><title>A\x00B</title></head><body>hello\x00world</body></html>"
    title, text = html_to_doc(html)
    assert "\x00" not in title
    assert "\x00" not in text
    assert title == "A B"
    assert "hello world" in text


# ==========================================
# Tests for extract_links
# ==========================================


def test_extract_links():
    base = "http://example.com"
    html = """
    <a href="/one">One</a>
    <a href="http://other.com">Other</a>
    <a href="#skip">Skip</a>
    """
    links = extract_links(base, html)
    assert "http://example.com/one" in links
    assert "http://other.com" in links


def test_extract_links_limit():
    base = "http://example.com"
    html = "".join([f'<a href="/page{i}">Link {i}</a>' for i in range(20)])
    links = extract_links(base, html)
    # Default limit in tasks.py is 50
    assert len(links) <= 50


def test_extract_links_relative():
    base = "http://example.com/dir/"
    html = '<a href="page.html">Link</a>'
    links = extract_links(base, html)
    assert "http://example.com/dir/page.html" in links


def test_extract_links_ignore_invalid():
    base = "http://example.com"
    html = """
    <a href="mailto:test@example.com">Email</a>
    <a href="javascript:void(0)">JS</a>
    <a href="http://valid.com">Valid</a>
    """
    links = extract_links(base, html)
    # Only valid HTTP(S) links should be included
    assert "http://valid.com" in links
    assert not any("mailto" in link for link in links)
    assert not any("javascript" in link for link in links)
