import pytest

from web_search_core.testing import ensure_test_pg
from web_search_core.url_admission import URLAdmissionPolicy
from web_search_postgres.migrate import migrate
from web_search_postgres.search import get_connection
from web_search_web_model import LinkGraphRepository


ensure_test_pg()


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    migrate()


@pytest.fixture(autouse=True)
def _clean_links():
    yield
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE links")
        conn.commit()
        cur.close()
    finally:
        conn.close()


@pytest.fixture
def link_graph() -> LinkGraphRepository:
    policy = URLAdmissionPolicy(
        drop_query_params=("utm_source",),
        reject_extensions=frozenset(),
        reject_path_prefixes=(),
        reject_path_contains=(),
        reject_query_params=frozenset(),
        domain_rules=(),
    )
    return LinkGraphRepository(policy)


def _fetch_links() -> list[tuple[str, str]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT src, dst FROM links ORDER BY src, dst")
        rows = [(str(src), str(dst)) for src, dst in cur.fetchall()]
        cur.close()
        return rows
    finally:
        conn.close()


def test_replace_observed_links_normalizes_and_dedupes(link_graph):
    count = link_graph.replace_observed_links(
        "https://Example.com/page",
        [
            "https://example.com/a?utm_source=test",
            "https://example.com/a",
            "https://example.com/page",
            "mailto:test@example.com",
        ],
    )

    assert count == 1
    assert _fetch_links() == [
        ("https://example.com/page", "https://example.com/a"),
    ]


def test_replace_observed_links_replaces_existing_rows(link_graph):
    link_graph.replace_observed_links(
        "https://example.com/page",
        ["https://example.com/old"],
    )

    count = link_graph.replace_observed_links(
        "https://example.com/page",
        ["https://example.com/new"],
    )

    assert count == 1
    assert _fetch_links() == [
        ("https://example.com/page", "https://example.com/new"),
    ]
