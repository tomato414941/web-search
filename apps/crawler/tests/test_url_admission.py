from __future__ import annotations

from web_search_crawler.services.url_admission import (
    URLAdmissionPolicy,
    load_url_admission_policy,
)


def _make_policy(**overrides) -> URLAdmissionPolicy:
    params = {
        "drop_query_params": (),
        "reject_extensions": frozenset(),
        "reject_path_prefixes": (),
        "reject_path_contains": (),
        "reject_query_params": frozenset(),
        "domain_rules": (),
    }
    params.update(overrides)
    return URLAdmissionPolicy(**params)


def test_url_admission_normalizes_tracking_params_and_host():
    policy = _make_policy(drop_query_params=("utm_source", "fbclid"))

    decision = policy.evaluate("HTTPS://Example.com/docs?id=1&utm_source=x&fbclid=y")

    assert decision.action == "allow"
    assert decision.normalized_url == "https://example.com/docs?id=1"


def test_url_admission_rejects_filtered_extension():
    policy = _make_policy(reject_extensions=frozenset({".jpg"}))

    decision = policy.evaluate("https://example.com/photo.jpg")

    assert decision.action == "reject"
    assert decision.reason_code == "filtered_extension"


def test_url_admission_rejects_filtered_path_prefix():
    policy = _make_policy(reject_path_prefixes=("/login",))

    decision = policy.evaluate("https://example.com/login/reset")

    assert decision.action == "reject"
    assert decision.reason_code == "filtered_path_prefix"


def test_url_admission_rejects_invalid_ipv6_host_without_brackets():
    policy = _make_policy()

    decision = policy.evaluate("http://2001:4860:a003::68/")

    assert decision.action == "reject"
    assert decision.reason_code == "invalid_url"


def test_load_url_admission_policy_from_yaml(tmp_path):
    path = tmp_path / "rules.yml"
    path.write_text(
        """
drop_query_params:
  - utm_source
reject_extensions:
  - .pdf
reject_path_prefixes:
  - /login
""".strip()
    )

    policy = load_url_admission_policy(path)

    assert (
        policy.evaluate("https://example.com/a.pdf").reason_code == "filtered_extension"
    )
    assert (
        policy.evaluate("https://example.com/login").reason_code
        == "filtered_path_prefix"
    )
    assert policy.evaluate("https://example.com/docs?utm_source=x").normalized_url == (
        "https://example.com/docs"
    )


def test_url_admission_rejects_domain_scoped_prefix_and_query_rules(tmp_path):
    path = tmp_path / "rules.yml"
    path.write_text(
        """
domain_rules:
  - domains:
      - blog.hatena.ne.jp
    reject_path_prefixes:
      - /-/share
  - domains:
      - www.amazon.co.jp
    reject_query_params:
      - tag
""".strip()
    )

    policy = load_url_admission_policy(path)

    assert (
        policy.evaluate("https://blog.hatena.ne.jp/-/share/mastodon?x=1").reason_code
        == "domain_path_prefix_denied"
    )
    assert (
        policy.evaluate("https://www.amazon.co.jp/dp/B000?tag=abc-22").reason_code
        == "domain_query_param_denied"
    )
