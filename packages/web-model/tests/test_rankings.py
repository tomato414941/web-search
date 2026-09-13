import os
from datetime import UTC, datetime
from uuid import uuid4

os.environ.setdefault("ENVIRONMENT", "test")

from web_search_core.testing import ensure_test_pg
from web_search_postgres.migrate import migrate
from web_search_postgres.search import get_connection
from web_search_web_model.archive.outbox import Batch
from web_search_web_model.archive.records import Observation
from web_search_web_model.archive.store import ObjectStore, publish_batch
from web_search_web_model.rankings import (
    calculate_domain_pagerank,
    calculate_pagerank,
)

ensure_test_pg()


def _reset_rank_tables() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        for table in ("page_ranks", "domain_ranks", "documents"):
            cur.execute(f"TRUNCATE {table} CASCADE")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _insert_document_graph(object_store) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO documents (url, title, content)
            VALUES (%s, %s, %s)
            """,
            [
                ("https://a.example/page", "A", "alpha"),
                ("https://b.example/page", "B", "bravo"),
                ("https://c.example/page", "C", "charlie"),
            ],
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    publish_batch(
        object_store,
        Batch(
            str(uuid4()),
            datetime.now(UTC),
            [
                Observation(
                    "https://a.example/page",
                    "a.example",
                    1,
                    "2026-01-01T00:00:00Z",
                    ["https://b.example/page", "https://c.example/page"],
                ),
                Observation(
                    "https://b.example/page",
                    "b.example",
                    2,
                    "2026-01-01T00:00:00Z",
                    ["https://c.example/page"],
                ),
            ],
        ),
    )


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


def test_calculate_pagerank_writes_page_scores(object_store, monkeypatch):
    migrate()
    _reset_rank_tables()
    _insert_document_graph(object_store)
    monkeypatch.setattr(ObjectStore, "from_env", lambda: object_store)

    count = calculate_pagerank(iterations=5)

    assert count == 3
    assert _count_rows("page_ranks") == 3


def test_calculate_domain_pagerank_writes_domain_scores(object_store, monkeypatch):
    migrate()
    _reset_rank_tables()
    _insert_document_graph(object_store)
    monkeypatch.setattr(ObjectStore, "from_env", lambda: object_store)

    count = calculate_domain_pagerank(iterations=5)

    assert count == 3
    assert _count_rows("domain_ranks") == 3
