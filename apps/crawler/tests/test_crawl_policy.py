from web_search_crawler.services.crawl_policy import (
    POLICIES,
    assign_crawl_policy,
    compute_failure_retry_delay,
    compute_success_recrawl_delay,
)
from web_search_crawler.services.frontier_budget import allocate_frontier_tier_budgets


def test_assign_crawl_policy_marks_manual_urls_as_manual_now():
    assignment = assign_crawl_policy(
        "https://example.com/path",
        discovered_via="manual",
    )

    assert assignment.crawl_profile == "manual_now"
    assert assignment.priority_bucket == 0


def test_assign_crawl_policy_marks_release_notes_paths():
    assignment = assign_crawl_policy(
        "https://docs.python.org/3/whatsnew/3.13.html",
        discovered_via="outlink",
    )

    assert assignment.crawl_profile == "release_notes"
    assert assignment.priority_bucket == 1
    assert POLICIES[assignment.crawl_profile].budget_tier == "hot"


def test_assign_crawl_policy_marks_canonical_docs_paths():
    assignment = assign_crawl_policy(
        "https://docs.docker.com/reference/cli/docker/",
        discovered_via="outlink",
    )

    assert assignment.crawl_profile == "canonical_docs"
    assert assignment.canonical_source == "docker_docs"


def test_assign_crawl_policy_marks_news_root_paths():
    assignment = assign_crawl_policy(
        "https://openai.com/news/",
        discovered_via="outlink",
    )

    assert assignment.crawl_profile == "news_root"


def test_assign_crawl_policy_marks_blog_root_paths():
    assignment = assign_crawl_policy(
        "https://example.com/blog/",
        discovered_via="outlink",
    )

    assert assignment.crawl_profile == "blog_root"


def test_assign_crawl_policy_marks_news_articles_as_article():
    assignment = assign_crawl_policy(
        "https://openai.com/news/some-update/",
        discovered_via="outlink",
    )

    assert assignment.crawl_profile == "article"


def test_compute_success_recrawl_delay_prefers_canonical_sources():
    delay = compute_success_recrawl_delay(
        "release_notes",
        canonical_source="python_docs",
    )

    assert delay == 1 * 3600


def test_compute_success_recrawl_delay_uses_news_root_canonical_interval():
    delay = compute_success_recrawl_delay(
        "news_root",
        canonical_source="openai_news",
    )

    assert delay == 2 * 3600


def test_compute_success_recrawl_delay_uses_blog_root_canonical_interval():
    delay = compute_success_recrawl_delay(
        "blog_root",
        canonical_source="example_blog",
    )

    assert delay == 4 * 3600


def test_compute_failure_retry_delay_scales_with_fail_streak():
    first = compute_failure_retry_delay("news_root", fail_streak=0)
    third = compute_failure_retry_delay("news_root", fail_streak=2)

    assert first == 30 * 60
    assert third == 2 * 3600


def test_allocate_frontier_tier_budgets_prefers_hot_then_reference():
    budgets = allocate_frontier_tier_budgets(2)

    assert [(budget.tier, budget.leases) for budget in budgets] == [
        ("hot", 1),
        ("reference", 1),
    ]
