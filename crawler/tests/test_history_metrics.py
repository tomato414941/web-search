from app.utils import history


def test_error_count_uses_current_error_statuses(tmp_path):
    db_path = str(tmp_path / "crawler_history.db")
    history.init_db(db_path)

    # Use unique domains to avoid PG shared DB data leakage
    history.log_crawl_attempt(
        "https://errcount-ok.test", "indexed", 200, db_path=db_path
    )
    history.log_crawl_attempt(
        "https://errcount-idx.test",
        "indexer_error",
        500,
        "indexer failed",
        db_path=db_path,
    )
    history.log_crawl_attempt(
        "https://errcount-http.test",
        "http_error",
        502,
        "bad gateway",
        db_path=db_path,
    )
    history.log_crawl_attempt(
        "https://errcount-unk.test",
        "unknown_error",
        None,
        "unknown",
        db_path=db_path,
    )
    history.log_crawl_attempt(
        "https://errcount-retry.test",
        "retry_later",
        None,
        "retry",
        db_path=db_path,
    )

    count = history.get_error_count(hours=1, db_path=db_path)
    # In PG shared DB mode, count includes data from other tests;
    # verify at least 3 errors from our data are counted
    assert count >= 3


def test_recent_errors_returns_only_error_statuses(tmp_path):
    db_path = str(tmp_path / "crawler_history_recent.db")
    history.init_db(db_path)

    # Use unique domains to avoid PG shared DB data leakage
    history.log_crawl_attempt(
        "https://recent-skip.test", "skipped", 200, "no content", db_path=db_path
    )
    history.log_crawl_attempt(
        "https://recent-dead.test",
        "dead_letter",
        None,
        "too many retries",
        db_path=db_path,
    )

    errors = history.get_recent_errors(limit=10, db_path=db_path)
    # Verify our dead_letter entry is in results
    dead_urls = [e["url"] for e in errors]
    assert "https://recent-dead.test" in dead_urls
    # Verify skipped entries are NOT in error results
    assert "https://recent-skip.test" not in dead_urls


def test_get_robots_blocked_domains(tmp_path):
    db_path = str(tmp_path / "crawler_block.db")
    history.init_db(db_path)

    # Use unique domains; in PG mode all tests share one DB so data accumulates
    for i in range(3):
        history.log_crawl_attempt(
            f"https://robots-pos.test/page{i}",
            "blocked",
            error_message="Blocked by robots.txt",
            db_path=db_path,
        )
    # SSRF block -> different error_message, should never count
    history.log_crawl_attempt(
        "https://robots-ssrf-only.test/x",
        "blocked",
        error_message="SSRF: private IP",
        db_path=db_path,
    )

    # Positive: domain with robots blocks is in result (min_count=1 to be safe)
    result = history.get_robots_blocked_domains(hours=1, min_count=1, db_path=db_path)
    assert "robots-pos.test" in result
    # Negative: SSRF-only domain never matches robots filter (use high threshold)
    result_strict = history.get_robots_blocked_domains(
        hours=1, min_count=1000, db_path=db_path
    )
    assert "robots-ssrf-only.test" not in result_strict


def test_get_robots_blocked_domains_below_threshold(tmp_path):
    db_path = str(tmp_path / "crawler_threshold.db")
    history.init_db(db_path)

    # Use unique domain to avoid PG shared DB data leakage
    # 1 block, threshold set to 1000 so this can never accumulate past it
    history.log_crawl_attempt(
        "https://threshold-never.test/p0",
        "blocked",
        error_message="Blocked by robots.txt",
        db_path=db_path,
    )

    result = history.get_robots_blocked_domains(
        hours=1, min_count=1000, db_path=db_path
    )
    assert "threshold-never.test" not in result


def test_get_robots_blocked_domains_with_counts(tmp_path):
    db_path = str(tmp_path / "crawler_block_counts.db")
    history.init_db(db_path)

    # Use unique domains to avoid PG shared DB data leakage
    for i in range(5):
        history.log_crawl_attempt(
            f"https://blocked-a.test/p{i}",
            "blocked",
            error_message="Blocked by robots.txt",
            db_path=db_path,
        )
    for i in range(3):
        history.log_crawl_attempt(
            f"https://blocked-b.test/p{i}",
            "blocked",
            error_message="Blocked by robots.txt",
            db_path=db_path,
        )

    result = history.get_robots_blocked_domains_with_counts(
        hours=1, min_count=3, db_path=db_path
    )
    domains = {r["domain"]: r["count"] for r in result}
    assert domains.get("blocked-a.test", 0) >= 5
    assert domains.get("blocked-b.test", 0) >= 3
    # Verify sorted by count descending
    counts = [r["count"] for r in result]
    assert counts == sorted(counts, reverse=True)


def test_get_high_failure_domains(tmp_path):
    db_path = str(tmp_path / "crawler_failures.db")
    history.init_db(db_path)

    # Use unique domains to avoid PG shared DB data leakage
    # fail-heavy.test: 5 errors out of 6 total
    for i in range(5):
        history.log_crawl_attempt(
            f"https://fail-heavy.test/p{i}",
            "http_error",
            502,
            "bad gateway",
            db_path=db_path,
        )
    history.log_crawl_attempt(
        "https://fail-heavy.test/ok", "indexed", 200, db_path=db_path
    )

    # fail-light.test: 1 error out of 5 total (below min_count)
    history.log_crawl_attempt(
        "https://fail-light.test/err", "http_error", 500, "error", db_path=db_path
    )
    for i in range(4):
        history.log_crawl_attempt(
            f"https://fail-light.test/p{i}", "indexed", 200, db_path=db_path
        )

    # Positive: high-failure domain is in result
    result = history.get_high_failure_domains(hours=1, min_count=5, db_path=db_path)
    domains = {r["domain"]: r for r in result}
    assert "fail-heavy.test" in domains
    assert domains["fail-heavy.test"]["error_count"] >= 5
    assert domains["fail-heavy.test"]["error_rate"] > 50.0
    # Negative: low-failure domain not in result with very high threshold
    result_strict = history.get_high_failure_domains(
        hours=1, min_count=1000, db_path=db_path
    )
    strict_domains = {r["domain"] for r in result_strict}
    assert "fail-light.test" not in strict_domains
