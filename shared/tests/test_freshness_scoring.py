"""Tests for freshness signal in BM25 scoring."""

from datetime import datetime, timedelta, timezone

from shared.postgres.search import get_connection
from shared.search_kernel.scoring import BM25Config, BM25Scorer


def _setup_db(pages: list[dict]):
    """Insert test data into the PG database (schema already exists via conftest)."""
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO index_stats (key, value) VALUES ('total_docs', %s), ('avg_doc_length', %s)",
            (len(pages), 100.0),
        )

        tokens_set: set[str] = set()
        for p in pages:
            cur.execute(
                "INSERT INTO documents (url, title, content, word_count, indexed_at) VALUES (%s, %s, %s, %s, %s)",
                (
                    p["url"],
                    p.get("title", ""),
                    p.get("content", ""),
                    p.get("wc", 100),
                    p["indexed_at"],
                ),
            )
            for token in p.get("tokens", []):
                cur.execute(
                    "INSERT INTO inverted_index (url, token, field, term_freq) VALUES (%s, %s, 'content', 1)",
                    (p["url"], token),
                )
                tokens_set.add(token)

        for token in tokens_set:
            doc_freq = sum(1 for p in pages if token in p.get("tokens", []))
            cur.execute(
                "INSERT INTO token_stats (token, doc_freq) VALUES (%s, %s)",
                (token, doc_freq),
            )

        conn.commit()
        cur.close()
    finally:
        conn.close()


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

    _setup_db(pages)

    config = BM25Config(pagerank_weight=0, freshness_weight=0.1)
    scorer = BM25Scorer(db_path=None, config=config)
    conn = get_connection()
    try:
        results = scorer.score_batch(
            conn, ["http://new.example.com", "http://old.example.com"], ["python"]
        )
        scores = {url: score for url, score in results}
    finally:
        conn.close()

    assert scores["http://new.example.com"] > scores["http://old.example.com"]


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

    _setup_db(pages)

    config = BM25Config(pagerank_weight=0, freshness_weight=0)
    scorer = BM25Scorer(db_path=None, config=config)
    conn = get_connection()
    try:
        results = scorer.score_batch(
            conn, ["http://new.example.com", "http://old.example.com"], ["python"]
        )
        scores = {url: score for url, score in results}
    finally:
        conn.close()

    assert (
        abs(scores["http://new.example.com"] - scores["http://old.example.com"]) < 1e-9
    )


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

    _setup_db(pages)

    config = BM25Config(pagerank_weight=0, freshness_weight=0.1)
    scorer = BM25Scorer(db_path=None, config=config)
    conn = get_connection()
    try:
        results = scorer.score_batch(
            conn, ["http://new.example.com", "http://null.example.com"], ["python"]
        )
        scores = {url: score for url, score in results}
    finally:
        conn.close()

    # New page gets freshness boost, null page doesn't
    assert scores["http://new.example.com"] > scores["http://null.example.com"]
    # Null page still has a positive score (BM25 only)
    assert scores["http://null.example.com"] > 0
