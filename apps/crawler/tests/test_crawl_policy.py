from web_search_crawler.services.crawl_policy import (
    POLICIES,
    assign_crawl_policy,
    compute_failure_retry_delay,
    compute_success_recrawl_delay,
)
from web_search_crawler.services.crawl_task_budget import (
    allocate_crawl_task_tier_budgets,
)


def test_assign_crawl_policy_applies_operator_priority_without_changing_profile():
    assignment = assign_crawl_policy(
        "https://docs.docker.com/reference/cli/docker/",
        admission_intent="operator_priority",
    )

    assert assignment.crawl_profile == "canonical_docs"
    assert assignment.priority_bucket == 0
    assert assignment.priority_score == 200.0


def test_assign_crawl_policy_marks_release_notes_paths():
    assignment = assign_crawl_policy(
        "https://docs.python.org/3/whatsnew/3.13.html",
    )

    assert assignment.crawl_profile == "release_notes"
    assert assignment.priority_bucket == 1
    assert POLICIES[assignment.crawl_profile].budget_tier == "hot"


def test_assign_crawl_policy_marks_canonical_docs_paths():
    assignment = assign_crawl_policy(
        "https://docs.docker.com/reference/cli/docker/",
    )

    assert assignment.crawl_profile == "canonical_docs"


def test_assign_crawl_policy_marks_news_root_paths():
    assignment = assign_crawl_policy(
        "https://openai.com/news/",
    )

    assert assignment.crawl_profile == "news_root"


def test_assign_crawl_policy_marks_blog_root_paths():
    assignment = assign_crawl_policy(
        "https://example.com/blog/",
    )

    assert assignment.crawl_profile == "blog_root"


def test_assign_crawl_policy_marks_news_articles_as_article():
    assignment = assign_crawl_policy(
        "https://openai.com/news/some-update/",
    )

    assert assignment.crawl_profile == "article"


def test_compute_success_recrawl_delay_uses_profile_base_interval():
    assert compute_success_recrawl_delay("release_notes") == 4 * 3600
    assert compute_success_recrawl_delay("news_root") == 4 * 3600
    assert compute_success_recrawl_delay("blog_root") == 8 * 3600


def test_compute_failure_retry_delay_scales_with_fail_streak():
    first = compute_failure_retry_delay("news_root", fail_streak=0)
    third = compute_failure_retry_delay("news_root", fail_streak=2)

    assert first == 30 * 60
    assert third == 2 * 3600


def test_allocate_crawl_task_tier_budgets_prefers_hot_then_reference():
    budgets = allocate_crawl_task_tier_budgets(2)

    assert [(budget.tier, budget.leases) for budget in budgets] == [
        ("hot", 1),
        ("reference", 1),
    ]
