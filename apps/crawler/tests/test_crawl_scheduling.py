from web_search_crawler.services.crawl_scheduling import (
    compute_admission_schedule,
    compute_failure_retry_delay_for_url,
    compute_success_recrawl_delay_for_url,
)


def test_compute_admission_schedule_applies_operator_priority():
    assignment = compute_admission_schedule(
        "https://docs.docker.com/reference/cli/docker/",
        admission_intent="operator_priority",
    )

    assert assignment.priority_bucket == 0


def test_compute_admission_schedule_prioritizes_release_notes_paths():
    assignment = compute_admission_schedule(
        "https://docs.python.org/3/whatsnew/3.13.html",
    )

    assert assignment.priority_bucket == 1
    assert (
        compute_success_recrawl_delay_for_url(
            "https://docs.python.org/3/whatsnew/3.13.html"
        )
        == 4 * 3600
    )


def test_compute_admission_schedule_prioritizes_reference_docs_paths():
    assignment = compute_admission_schedule(
        "https://docs.docker.com/reference/cli/docker/",
    )

    assert assignment.priority_bucket == 1
    assert (
        compute_success_recrawl_delay_for_url(
            "https://docs.docker.com/reference/cli/docker/"
        )
        == 7 * 24 * 3600
    )


def test_compute_admission_schedule_prioritizes_news_root_paths():
    assignment = compute_admission_schedule(
        "https://openai.com/news/",
    )

    assert assignment.priority_bucket == 1
    assert compute_success_recrawl_delay_for_url("https://openai.com/news/") == 4 * 3600


def test_compute_admission_schedule_prioritizes_blog_root_paths():
    assignment = compute_admission_schedule(
        "https://example.com/blog/",
    )

    assert assignment.priority_bucket == 1
    assert (
        compute_success_recrawl_delay_for_url("https://example.com/blog/") == 8 * 3600
    )


def test_compute_admission_schedule_prioritizes_news_article_paths_below_roots():
    assignment = compute_admission_schedule(
        "https://openai.com/news/some-update/",
    )

    assert assignment.priority_bucket == 2
    assert (
        compute_success_recrawl_delay_for_url("https://openai.com/news/some-update/")
        == 30 * 24 * 3600
    )


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
