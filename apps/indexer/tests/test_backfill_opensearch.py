from datetime import UTC, datetime

from web_search_indexer.cli import backfill_opensearch


def test_backfill_rebuilds_projection_without_count_skip(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    class FakeClient:
        def count(self, *args, **kwargs):
            raise AssertionError("backfill should not skip based on OpenSearch count")

    indexed_docs = []

    monkeypatch.setattr(backfill_opensearch, "get_client", lambda url: FakeClient())
    monkeypatch.setattr(backfill_opensearch, "ensure_index", lambda client: None)
    monkeypatch.setattr(
        backfill_opensearch.DocumentRepository,
        "count_documents",
        staticmethod(lambda: 1),
    )
    monkeypatch.setattr(
        backfill_opensearch.DocumentRepository,
        "fetch_documents_for_opensearch",
        staticmethod(
            lambda *, limit, offset: (
                [
                    (
                        "https://example.com/post",
                        "Example Title",
                        "Example content with facts.",
                        4,
                        datetime(2026, 1, 1, tzinfo=UTC),
                        datetime(2025, 12, 31, tzinfo=UTC),
                        "Ada",
                        "Example Org",
                    )
                ]
                if offset == 0
                else []
            )
        ),
    )
    monkeypatch.setattr(
        backfill_opensearch.DocumentRepository,
        "fetch_link_rank_map",
        staticmethod(lambda urls: {"https://example.com/post": (0.7, 0.3)}),
    )
    monkeypatch.setattr(
        backfill_opensearch,
        "bulk_index",
        lambda client, docs: indexed_docs.extend(docs) or len(docs),
    )

    backfill_opensearch.backfill(batch_size=100, opensearch_url="http://opensearch")

    assert len(indexed_docs) == 1
    doc = indexed_docs[0]
    assert doc["url"] == "https://example.com/post"
    assert doc["page_rank"] == 0.7
    assert doc["domain_rank"] == 0.3
    assert doc["published_at_present"] is True
    assert doc["author"] == "Ada"
    assert doc["organization"] == "Example Org"
