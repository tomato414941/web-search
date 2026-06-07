from web_search_crawler.services.crawl_policy import (
    assign_crawl_policy,
    compute_failure_retry_delay_for_url,
    compute_success_recrawl_delay_for_url,
)


def test_assign_crawl_policy_applies_operator_priority_without_changing_policy():
    assignment = assign_crawl_policy(
        "https://docs.docker.com/reference/cli/docker/",
        admission_intent="operator_priority",
    )

    assert assignment.policy_name == "reference_docs"
    assert assignment.priority_bucket == 0
    assert assignment.priority_score == 200.0


def test_assign_crawl_policy_marks_release_notes_paths():
    assignment = assign_crawl_policy(
        "https://docs.python.org/3/whatsnew/3.13.html",
    )

    assert assignment.policy_name == "release_notes"
    assert assignment.priority_bucket == 1


def test_assign_crawl_policy_marks_reference_docs_paths():
    assignment = assign_crawl_policy(
        "https://docs.docker.com/reference/cli/docker/",
    )

    assert assignment.policy_name == "reference_docs"


def test_assign_crawl_policy_marks_news_root_paths():
    assignment = assign_crawl_policy(
        "https://openai.com/news/",
    )

    assert assignment.policy_name == "news_root"


def test_assign_crawl_policy_marks_blog_root_paths():
    assignment = assign_crawl_policy(
        "https://example.com/blog/",
    )

    assert assignment.policy_name == "blog_root"


def test_assign_crawl_policy_marks_news_articles_as_article():
    assignment = assign_crawl_policy(
        "https://openai.com/news/some-update/",
    )

    assert assignment.policy_name == "article"


def test_compute_success_recrawl_delay_uses_policy_base_interval():
    assert (
        compute_success_recrawl_delay_for_url(
            "https://docs.python.org/3/whatsnew/3.13.html"
        )
        == 4 * 3600
    )
    assert compute_success_recrawl_delay_for_url("https://openai.com/news/") == 4 * 3600
    assert (
        compute_success_recrawl_delay_for_url("https://example.com/blog/") == 8 * 3600
    )


def test_compute_failure_retry_delay_scales_with_fail_streak():
    first = compute_failure_retry_delay_for_url(
        "https://openai.com/news/",
        fail_streak=0,
    )
    third = compute_failure_retry_delay_for_url(
        "https://openai.com/news/",
        fail_streak=2,
    )

    assert first == 30 * 60
    assert third == 2 * 3600
