from web_search_postgres.repositories import DocumentRepository
from web_search_postgres.search import get_connection


def _insert_url_referring_hosts(rows: list[tuple[str, str]]) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO url_referring_hosts (dst_url, referring_host)
            VALUES (%s, %s)
            """,
            rows,
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def test_fetch_referring_host_count_map_counts_distinct_referring_hosts():
    _insert_url_referring_hosts(
        [
            ("https://example.com/a", "docs.python.org"),
            ("https://example.com/a", "github.com"),
            ("https://example.com/b", "github.com"),
        ]
    )

    counts = DocumentRepository.fetch_referring_host_count_map(
        [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/missing",
        ]
    )

    assert counts == {
        "https://example.com/a": 2,
        "https://example.com/b": 1,
        "https://example.com/missing": 0,
    }


def test_fetch_referring_host_count_map_returns_empty_for_empty_urls():
    assert DocumentRepository.fetch_referring_host_count_map([]) == {}
