from shared.core.utils import normalize_url


def test_normalize_basic():
    # If link is absolute, base is ignored by urljoin
    assert (
        normalize_url("http://base.com", "http://example.com") == "http://example.com"
    )
    assert (
        normalize_url("http://base.com", "http://example.com/") == "http://example.com/"
    )


def test_normalize_relative_resolution():
    # Resolving relative paths
    base = "http://example.com/foo/bar.html"

    # Simple relative
    assert normalize_url(base, "baz.html") == "http://example.com/foo/baz.html"

    # Parent relative
    assert normalize_url(base, "../baz.html") == "http://example.com/baz.html"

    # Root relative
    assert normalize_url(base, "/baz.html") == "http://example.com/baz.html"


def test_normalize_scheme_and_case():
    # Lowercase scheme and host
    assert (
        normalize_url("http://base.com", "HTTP://EXAMPLE.COM/Foo")
        == "http://example.com/Foo"
    )


def test_normalize_fragments():
    # Fragments should be stripped
    assert (
        normalize_url("", "http://example.com/foo#section1") == "http://example.com/foo"
    )


def test_normalize_query_params():
    # Query parameters should be preserved
    url = "http://example.com/search?q=test&page=1"
    assert normalize_url("", url) == url


def test_normalize_garbage():
    # Empty or invalid
    assert normalize_url("", "") is None
    assert normalize_url("", None) is None
    # mailto should be ignored/handled
    assert normalize_url("", "mailto:user@example.com") is None
    # javascript: should be ignored
    assert normalize_url("", "javascript:alert(1)") is None
