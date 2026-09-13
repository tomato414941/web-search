import pytest

from web_search_core.testing import ensure_test_pg
from web_search_core.url_admission import URLAdmissionPolicy
from web_search_postgres.migrate import migrate
from web_search_postgres.search import get_connection
from web_search_web_model import LinkGraphRepository
from web_search_web_model.archive.records import Observation


ensure_test_pg()


@pytest.fixture(scope="session", autouse=True)
def _init_schema():
    migrate()


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
        cur.execute("SELECT payload FROM link_outbox ORDER BY revision")
        latest = {}
        for (payload,) in cur.fetchall():
            record = Observation.decode(payload)
            latest[record.src] = record.outlinks
        rows = sorted(
            (src, dst) for src, outlinks in latest.items() for dst in outlinks
        )
        cur.close()
        return rows
    finally:
        conn.close()


def _fetch_url_referring_hosts() -> list[tuple[str, str, bool]]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT dst_url, referring_host, first_observed_at <= last_observed_at
            FROM url_referring_hosts
            ORDER BY dst_url, referring_host
            """
        )
        rows = [
            (str(dst_url), str(referring_host), bool(observed_ordered))
            for dst_url, referring_host, observed_ordered in cur.fetchall()
        ]
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
    assert _fetch_url_referring_hosts() == [
        ("https://example.com/a", "example.com", True),
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
    assert _fetch_url_referring_hosts() == [
        ("https://example.com/new", "example.com", True),
        ("https://example.com/old", "example.com", True),
    ]


def test_empty_observation_is_persisted_and_discoveries_stay_known(link_graph):
    from web_search_web_model.archive.outbox import transaction

    link_graph.replace_observed_links(
        "https://example.com/page", ["https://other.example/target"]
    )
    link_graph.replace_observed_links("https://example.com/page", [])
    assert _fetch_links() == []
    with transaction() as cur:
        cur.execute("SELECT payload FROM link_outbox ORDER BY revision")
        records = [Observation.decode(row[0]) for row in cur]
        cur.execute("SELECT url FROM urls ORDER BY url")
        urls = [row[0] for row in cur]
    assert records[1].revision > records[0].revision > 0
    assert records[1].outlinks == []
    assert records[1].observed_at.endswith("Z")
    assert urls == ["https://example.com/page", "https://other.example/target"]


def test_observation_and_referring_hosts_roll_back_together(link_graph, monkeypatch):
    from web_search_web_model.archive.outbox import status

    def fail(*args):
        raise RuntimeError("referring host write failed")

    monkeypatch.setattr(link_graph, "_upsert_url_referring_hosts", fail)
    with pytest.raises(RuntimeError):
        link_graph.replace_observed_links(
            "https://example.com/page", ["https://other.example/target"]
        )
    assert status()["pending_bytes"] == 0
    assert status()["pending_pages"] == 0
