"""Test utility functions."""

import pytest

from shared.core import utils
from shared.core.utils import is_private_ip, normalize_url, resolve_is_private_async


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


class TestSSRFPrevention:
    """Test SSRF prevention utilities."""

    def test_block_localhost_ipv4(self):
        assert is_private_ip("127.0.0.1") is True

    def test_block_localhost_ipv6(self):
        assert is_private_ip("::1") is True

    def test_block_10_network(self):
        assert is_private_ip("10.0.0.1") is True

    def test_block_172_16_network(self):
        assert is_private_ip("172.16.0.1") is True

    def test_block_192_168_network(self):
        assert is_private_ip("192.168.1.1") is True

    def test_block_metadata_ip(self):
        assert is_private_ip("169.254.169.254") is True

    def test_block_zero_ip(self):
        assert is_private_ip("0.0.0.0") is True

    def test_allow_public_ip(self):
        assert is_private_ip("8.8.8.8") is False

    def test_allow_hostname(self):
        assert is_private_ip("example.com") is False

    def test_block_empty(self):
        assert is_private_ip("") is True

    def test_normalize_url_blocks_private_ip(self):
        result = normalize_url(
            "http://example.com", "http://127.0.0.1:5432/", block_private=True
        )
        assert result is None

    def test_normalize_url_blocks_metadata(self):
        result = normalize_url(
            "http://example.com",
            "http://169.254.169.254/latest/meta-data/",
            block_private=True,
        )
        assert result is None

    def test_normalize_url_allows_public_without_flag(self):
        result = normalize_url("http://example.com", "http://127.0.0.1/")
        assert result is not None  # block_private=False by default

    def test_normalize_url_allows_public_ip(self):
        result = normalize_url(
            "http://example.com", "http://8.8.8.8/page", block_private=True
        )
        assert result == "http://8.8.8.8/page"


class TestResolveIsPrivateAsync:
    """Test async DNS resolution SSRF check."""

    @pytest.mark.asyncio
    async def test_block_private_ip_literal(self):
        assert await resolve_is_private_async("127.0.0.1") is True

    @pytest.mark.asyncio
    async def test_block_metadata_ip(self):
        assert await resolve_is_private_async("169.254.169.254") is True

    @pytest.mark.asyncio
    async def test_block_unresolvable_host(self):
        assert (
            await resolve_is_private_async("this.host.does.not.exist.invalid") is True
        )

    @pytest.mark.asyncio
    async def test_allow_public_host(self):
        assert await resolve_is_private_async("example.com") is False

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_dns(self, monkeypatch):
        utils._ssrf_cache.clear()
        utils._ssrf_cache["cached.example.com"] = False
        call_count = 0
        original = utils.asyncio.get_running_loop

        def patched_loop():
            loop = original()
            orig_getaddrinfo = loop.getaddrinfo

            async def counting_getaddrinfo(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return await orig_getaddrinfo(*args, **kwargs)

            loop.getaddrinfo = counting_getaddrinfo
            return loop

        monkeypatch.setattr(utils.asyncio, "get_running_loop", patched_loop)
        result = await resolve_is_private_async("cached.example.com")
        assert result is False
        assert call_count == 0
        utils._ssrf_cache.clear()
