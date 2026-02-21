from app.utils import history


def test_error_count_uses_current_error_statuses(tmp_path):
    db_path = str(tmp_path / "crawler_history.db")
    history.init_db(db_path)

    history.log_crawl_attempt("https://ok.example", "indexed", 200, db_path=db_path)
    history.log_crawl_attempt(
        "https://indexer.example",
        "indexer_error",
        500,
        "indexer failed",
        db_path=db_path,
    )
    history.log_crawl_attempt(
        "https://http.example",
        "http_error",
        502,
        "bad gateway",
        db_path=db_path,
    )
    history.log_crawl_attempt(
        "https://unknown.example",
        "unknown_error",
        None,
        "unknown",
        db_path=db_path,
    )
    history.log_crawl_attempt(
        "https://retry.example",
        "retry_later",
        None,
        "retry",
        db_path=db_path,
    )

    count = history.get_error_count(hours=1, db_path=db_path)
    assert count == 3


def test_recent_errors_returns_only_error_statuses(tmp_path):
    db_path = str(tmp_path / "crawler_history_recent.db")
    history.init_db(db_path)

    history.log_crawl_attempt(
        "https://skip.example", "skipped", 200, "no content", db_path=db_path
    )
    history.log_crawl_attempt(
        "https://dead.example",
        "dead_letter",
        None,
        "too many retries",
        db_path=db_path,
    )

    errors = history.get_recent_errors(limit=10, db_path=db_path)
    assert len(errors) == 1
    assert errors[0]["url"] == "https://dead.example"


def test_get_robots_blocked_domains(tmp_path):
    db_path = str(tmp_path / "crawler_block.db")
    history.init_db(db_path)

    # 3 blocks from twitter.com -> should be in result (meets threshold)
    for i in range(3):
        history.log_crawl_attempt(
            f"https://twitter.com/page{i}",
            "blocked",
            error_message="Blocked by robots.txt",
            db_path=db_path,
        )
    # 1 block from example.com -> below threshold
    history.log_crawl_attempt(
        "https://example.com/page",
        "blocked",
        error_message="Blocked by robots.txt",
        db_path=db_path,
    )
    # SSRF block -> should not count (different error_message)
    history.log_crawl_attempt(
        "https://private.example/x",
        "blocked",
        error_message="SSRF: private IP",
        db_path=db_path,
    )

    result = history.get_robots_blocked_domains(hours=1, min_count=3, db_path=db_path)
    assert "twitter.com" in result
    assert "example.com" not in result
    assert "private.example" not in result


def test_get_robots_blocked_domains_below_threshold(tmp_path):
    db_path = str(tmp_path / "crawler_threshold.db")
    history.init_db(db_path)

    # 2 blocks (below default threshold of 3)
    for i in range(2):
        history.log_crawl_attempt(
            f"https://low.example/p{i}",
            "blocked",
            error_message="Blocked by robots.txt",
            db_path=db_path,
        )

    result = history.get_robots_blocked_domains(hours=1, min_count=3, db_path=db_path)
    assert "low.example" not in result
