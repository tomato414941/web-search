"""Tests for crawler denylist module."""

from app.core.crawl_denylist import is_domain_denied, load_crawl_denylist


class TestLoadCrawlDenylist:
    def test_loads_domains_from_file(self, tmp_path):
        f = tmp_path / "crawl_denylist.txt"
        f.write_text("facebook.com\nlinkedin.com\n")
        result = load_crawl_denylist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        f = tmp_path / "crawl_denylist.txt"
        f.write_text("# Comment\n\nfacebook.com\n  \n# Another\nlinkedin.com\n")
        result = load_crawl_denylist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_lowercases_domains(self, tmp_path):
        f = tmp_path / "crawl_denylist.txt"
        f.write_text("Facebook.COM\nLINKEDIN.com\n")
        result = load_crawl_denylist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_strips_whitespace(self, tmp_path):
        f = tmp_path / "crawl_denylist.txt"
        f.write_text("  facebook.com  \n  linkedin.com\n")
        result = load_crawl_denylist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_missing_file_returns_empty(self):
        result = load_crawl_denylist("/nonexistent/path.txt")
        assert result == frozenset()

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "crawl_denylist.txt"
        f.write_text("")
        result = load_crawl_denylist(f)
        assert result == frozenset()


class TestIsDomainDenied:
    DENYLIST = frozenset({"facebook.com", "linkedin.com", "donate.wikimedia.org"})

    def test_exact_match(self):
        assert is_domain_denied("facebook.com", self.DENYLIST) is True

    def test_subdomain_match(self):
        assert is_domain_denied("www.facebook.com", self.DENYLIST) is True
        assert is_domain_denied("m.facebook.com", self.DENYLIST) is True

    def test_deep_subdomain_match(self):
        assert is_domain_denied("cdn.www.facebook.com", self.DENYLIST) is True

    def test_no_false_positive_suffix(self):
        assert is_domain_denied("notfacebook.com", self.DENYLIST) is False

    def test_specific_subdomain_denylist(self):
        assert is_domain_denied("donate.wikimedia.org", self.DENYLIST) is True
        assert is_domain_denied("www.donate.wikimedia.org", self.DENYLIST) is True
        assert is_domain_denied("wikimedia.org", self.DENYLIST) is False
        assert is_domain_denied("en.wikimedia.org", self.DENYLIST) is False

    def test_case_insensitive(self):
        assert is_domain_denied("FACEBOOK.COM", self.DENYLIST) is True
        assert is_domain_denied("Www.Facebook.Com", self.DENYLIST) is True

    def test_empty_denylist(self):
        assert is_domain_denied("facebook.com", frozenset()) is False

    def test_unblocked_domain(self):
        assert is_domain_denied("example.com", self.DENYLIST) is False
        assert is_domain_denied("google.com", self.DENYLIST) is False
