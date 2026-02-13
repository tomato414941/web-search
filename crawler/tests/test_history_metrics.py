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
