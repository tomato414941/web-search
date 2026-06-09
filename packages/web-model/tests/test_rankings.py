import os

os.environ.setdefault("ENVIRONMENT", "test")

from web_search_core.testing import ensure_test_pg
from web_search_postgres.migrate import migrate
from web_search_postgres.search import get_connection
from web_search_web_model.rankings import (
    calculate_domain_pagerank,
    calculate_pagerank,
)

ensure_test_pg()


def _reset_rank_tables() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        for table in ("page_ranks", "domain_ranks", "documents", "links"):
            cur.execute(f"TRUNCATE {table} CASCADE")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _insert_document_graph() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO documents (url, title, content, word_count)
            VALUES (%s, %s, %s, %s)
            """,
            [
                ("https://a.example/page", "A", "alpha", 1),
                ("https://b.example/page", "B", "bravo", 1),
                ("https://c.example/page", "C", "charlie", 1),
            ],
        )
        cur.executemany(
            "INSERT INTO links (src, dst) VALUES (%s, %s)",
            [
                ("https://a.example/page", "https://b.example/page"),
                ("https://b.example/page", "https://c.example/page"),
                ("https://a.example/page", "https://c.example/page"),
            ],
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _count_rows(table: str) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        row = cur.fetchone()
        cur.close()
        return int(row[0])
    finally:
        conn.close()


def test_calculate_pagerank_writes_page_scores():
    migrate()
    _reset_rank_tables()
    _insert_document_graph()

    count = calculate_pagerank(iterations=5)

    assert count == 3
    assert _count_rows("page_ranks") == 3


def test_calculate_domain_pagerank_writes_domain_scores():
    migrate()
    _reset_rank_tables()
    _insert_document_graph()

    count = calculate_domain_pagerank(iterations=5)

    assert count == 3
    assert _count_rows("domain_ranks") == 3
