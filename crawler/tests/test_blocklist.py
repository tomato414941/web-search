"""Tests for domain blocklist module."""

from app.core.blocklist import is_domain_blocked, load_domain_blocklist


class TestLoadDomainBlocklist:
    def test_loads_domains_from_file(self, tmp_path):
        f = tmp_path / "blocklist.txt"
        f.write_text("facebook.com\nlinkedin.com\n")
        result = load_domain_blocklist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        f = tmp_path / "blocklist.txt"
        f.write_text("# Comment\n\nfacebook.com\n  \n# Another\nlinkedin.com\n")
        result = load_domain_blocklist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_lowercases_domains(self, tmp_path):
        f = tmp_path / "blocklist.txt"
        f.write_text("Facebook.COM\nLINKEDIN.com\n")
        result = load_domain_blocklist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_strips_whitespace(self, tmp_path):
        f = tmp_path / "blocklist.txt"
        f.write_text("  facebook.com  \n  linkedin.com\n")
        result = load_domain_blocklist(f)
        assert result == frozenset({"facebook.com", "linkedin.com"})

    def test_missing_file_returns_empty(self):
        result = load_domain_blocklist("/nonexistent/path.txt")
        assert result == frozenset()

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "blocklist.txt"
        f.write_text("")
        result = load_domain_blocklist(f)
        assert result == frozenset()


class TestIsDomainBlocked:
    BLOCKLIST = frozenset({"facebook.com", "linkedin.com", "donate.wikimedia.org"})

    def test_exact_match(self):
        assert is_domain_blocked("facebook.com", self.BLOCKLIST) is True

    def test_subdomain_match(self):
        assert is_domain_blocked("www.facebook.com", self.BLOCKLIST) is True
        assert is_domain_blocked("m.facebook.com", self.BLOCKLIST) is True

    def test_deep_subdomain_match(self):
        assert is_domain_blocked("cdn.www.facebook.com", self.BLOCKLIST) is True

    def test_no_false_positive_suffix(self):
        assert is_domain_blocked("notfacebook.com", self.BLOCKLIST) is False

    def test_specific_subdomain_blocklist(self):
        assert is_domain_blocked("donate.wikimedia.org", self.BLOCKLIST) is True
        assert is_domain_blocked("www.donate.wikimedia.org", self.BLOCKLIST) is True
        # wikimedia.org itself is NOT blocked (only donate.wikimedia.org)
        assert is_domain_blocked("wikimedia.org", self.BLOCKLIST) is False
        assert is_domain_blocked("en.wikimedia.org", self.BLOCKLIST) is False

    def test_case_insensitive(self):
        assert is_domain_blocked("FACEBOOK.COM", self.BLOCKLIST) is True
        assert is_domain_blocked("Www.Facebook.Com", self.BLOCKLIST) is True

    def test_empty_blocklist(self):
        assert is_domain_blocked("facebook.com", frozenset()) is False

    def test_unblocked_domain(self):
        assert is_domain_blocked("example.com", self.BLOCKLIST) is False
        assert is_domain_blocked("google.com", self.BLOCKLIST) is False
