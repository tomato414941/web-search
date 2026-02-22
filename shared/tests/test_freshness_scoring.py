"""Tests for freshness signal in BM25 scoring."""

import sqlite3
from datetime import datetime, timedelta, timezone

from shared.search.scoring import BM25Config, BM25Scorer


def _setup_db(conn: sqlite3.Connection, pages: list[dict]):
    """Set up an in-memory DB with test data."""
    conn.execute("CREATE TABLE index_stats (key TEXT PRIMARY KEY, value REAL)")
    conn.execute(
        "CREATE TABLE documents (url TEXT PRIMARY KEY, title TEXT, content TEXT, word_count INTEGER, indexed_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE inverted_index (url TEXT, token TEXT, field TEXT, term_freq INTEGER)"
    )
    conn.execute("CREATE TABLE token_stats (token TEXT PRIMARY KEY, doc_freq INTEGER)")
    conn.execute("CREATE TABLE page_ranks (url TEXT PRIMARY KEY, score REAL)")
    conn.execute("CREATE TABLE domain_ranks (domain TEXT PRIMARY KEY, score REAL)")

    conn.execute(
        "INSERT INTO index_stats VALUES ('total_docs', ?), ('avg_doc_length', ?)",
        (len(pages), 100.0),
    )

    tokens_set: set[str] = set()
    for p in pages:
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
            (
                p["url"],
                p.get("title", ""),
                p.get("content", ""),
                p.get("wc", 100),
                p["indexed_at"],
            ),
        )
        for token in p.get("tokens", []):
            conn.execute(
                "INSERT INTO inverted_index VALUES (?, ?, 'content', 1)",
                (p["url"], token),
            )
            tokens_set.add(token)

    for token in tokens_set:
        doc_freq = sum(1 for p in pages if token in p.get("tokens", []))
        conn.execute("INSERT INTO token_stats VALUES (?, ?)", (token, doc_freq))

    conn.commit()


def test_fresh_page_scores_higher():
    """A recently indexed page should score higher than an old page."""
    now = datetime.now(timezone.utc)
    pages = [
        {
            "url": "http://new.example.com",
            "indexed_at": now.isoformat(),
            "tokens": ["python"],
            "wc": 100,
        },
        {
            "url": "http://old.example.com",
            "indexed_at": (now - timedelta(days=365)).isoformat(),
            "tokens": ["python"],
            "wc": 100,
        },
    ]

    conn = sqlite3.connect(":memory:")
    _setup_db(conn, pages)

    config = BM25Config(pagerank_weight=0, freshness_weight=0.1)
    scorer = BM25Scorer(db_path=":memory:", config=config)
    results = scorer.score_batch(
        conn, ["http://new.example.com", "http://old.example.com"], ["python"]
    )
    scores = {url: score for url, score in results}

    assert scores["http://new.example.com"] > scores["http://old.example.com"]
    conn.close()


def test_freshness_disabled_when_weight_zero():
    """With freshness_weight=0, both pages should score the same."""
    now = datetime.now(timezone.utc)
    pages = [
        {
            "url": "http://new.example.com",
            "indexed_at": now.isoformat(),
            "tokens": ["python"],
            "wc": 100,
        },
        {
            "url": "http://old.example.com",
            "indexed_at": (now - timedelta(days=365)).isoformat(),
            "tokens": ["python"],
            "wc": 100,
        },
    ]

    conn = sqlite3.connect(":memory:")
    _setup_db(conn, pages)

    config = BM25Config(pagerank_weight=0, freshness_weight=0)
    scorer = BM25Scorer(db_path=":memory:", config=config)
    results = scorer.score_batch(
        conn, ["http://new.example.com", "http://old.example.com"], ["python"]
    )
    scores = {url: score for url, score in results}

    assert (
        abs(scores["http://new.example.com"] - scores["http://old.example.com"]) < 1e-9
    )
    conn.close()


def test_freshness_with_null_indexed_at():
    """Pages without indexed_at should get no freshness boost but still score."""
    now = datetime.now(timezone.utc)
    pages = [
        {
            "url": "http://new.example.com",
            "indexed_at": now.isoformat(),
            "tokens": ["python"],
            "wc": 100,
        },
        {
            "url": "http://null.example.com",
            "indexed_at": None,
            "tokens": ["python"],
            "wc": 100,
        },
    ]

    conn = sqlite3.connect(":memory:")
    _setup_db(conn, pages)

    config = BM25Config(pagerank_weight=0, freshness_weight=0.1)
    scorer = BM25Scorer(db_path=":memory:", config=config)
    results = scorer.score_batch(
        conn, ["http://new.example.com", "http://null.example.com"], ["python"]
    )
    scores = {url: score for url, score in results}

    # New page gets freshness boost, null page doesn't
    assert scores["http://new.example.com"] > scores["http://null.example.com"]
    # Null page still has a positive score (BM25 only)
    assert scores["http://null.example.com"] > 0
    conn.close()
