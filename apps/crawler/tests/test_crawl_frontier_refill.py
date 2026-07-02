from urllib.parse import urlparse

from web_search_crawler.db.connection import db_connection, db_transaction
from web_search_crawler.services.crawl_frontier_refill import (
    fetch_link_frontier_candidates,
    refill_crawl_frontier_from_links,
)
from web_search_web_model import UrlLedgerRepository


def _insert_links(rows: list[tuple[str, str]]) -> None:
    with db_transaction("/unused") as cur:
        cur.executemany(
            "INSERT INTO links (src, dst) VALUES (%s, %s)",
            rows,
        )


def _insert_document(url: str) -> None:
    with db_transaction("/unused") as cur:
        cur.execute(
            """
            INSERT INTO documents (url, title, content)
            VALUES (%s, %s, %s)
            """,
            (url, "Indexed", "Already indexed"),
        )


def _queue_contains(url: str) -> bool:
    with db_connection("/unused") as cur:
        cur.execute("SELECT 1 FROM crawl_queue WHERE url = %s", (url,))
        return cur.fetchone() is not None


def test_fetch_link_frontier_candidates_excludes_indexed_and_queued_urls(
    test_url_store,
):
    indexed = "https://indexed.example.com/page"
    queued = "https://queued.example.com/page"
    new_a = "https://new.example.com/a"
    new_b = "https://new.example.com/b"
    other = "https://other.example.com/a"
    _insert_document(indexed)
    test_url_store.enqueue_url_for_crawl(queued)
    _insert_links(
        [
            ("https://source-a.example.com/page", indexed),
            ("https://source-b.example.com/page", queued),
            ("https://source-c.example.com/page", new_a),
            ("https://source-d.example.com/page", new_b),
            ("https://source-e.example.com/page", other),
        ]
    )

    candidates = fetch_link_frontier_candidates(
        limit=10,
        sample_percent=100,
        sample_limit=100,
        statement_timeout_ms=5_000,
    )

    assert indexed not in candidates
    assert queued not in candidates
    assert other in candidates
    assert (
        len([url for url in candidates if urlparse(url).hostname == "new.example.com"])
        == 1
    )


def test_refill_crawl_frontier_from_links_enqueues_candidates(test_url_store):
    first = "https://first.example.com/a"
    second = "https://second.example.com/a"
    _insert_links(
        [
            ("https://source-a.example.com/page", first),
            ("https://source-b.example.com/page", second),
        ]
    )
    url_ledger = UrlLedgerRepository(test_url_store.url_admission_policy)

    result = refill_crawl_frontier_from_links(
        store=test_url_store,
        url_ledger=url_ledger,
        limit=10,
        sample_percent=100,
        sample_limit=100,
        statement_timeout_ms=5_000,
    )

    assert result.candidates == 2
    assert result.recorded == 2
    assert result.enqueued == 2
    assert all(_queue_contains(url) for url in result.urls)
