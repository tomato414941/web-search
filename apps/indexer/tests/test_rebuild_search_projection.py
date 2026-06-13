from datetime import UTC, datetime

from web_search_indexer.cli import rebuild_search_projection


def test_rebuild_search_projection_does_not_skip_when_counts_match(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    class FakeClient:
        def count(self, *args, **kwargs):
            raise AssertionError(
                "search projection rebuild should not skip based on OpenSearch count"
            )

    indexed_docs = []

    monkeypatch.setattr(
        rebuild_search_projection, "get_client", lambda url: FakeClient()
    )
    monkeypatch.setattr(rebuild_search_projection, "ensure_index", lambda client: None)
    monkeypatch.setattr(
        rebuild_search_projection.DocumentRepository,
        "count_documents",
        staticmethod(lambda: 1),
    )
    monkeypatch.setattr(
        rebuild_search_projection.DocumentRepository,
        "fetch_documents_for_opensearch",
        staticmethod(
            lambda *, limit, offset: (
                [
                    (
                        "https://example.com/post",
                        "Example Title",
                        "Example content with facts.",
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
        rebuild_search_projection.DocumentRepository,
        "fetch_link_rank_map",
        staticmethod(lambda urls: {"https://example.com/post": (0.7, 0.3)}),
    )
    monkeypatch.setattr(
        rebuild_search_projection,
        "bulk_index",
        lambda client, docs: indexed_docs.extend(docs) or len(docs),
    )

    rebuild_search_projection.rebuild_search_projection(
        batch_size=100, opensearch_url="http://opensearch"
    )

    assert len(indexed_docs) == 1
    doc = indexed_docs[0]
    assert doc["url"] == "https://example.com/post"
    assert doc["page_rank"] == 0.7
    assert doc["domain_rank"] == 0.3
    assert doc["published_at"] == "2025-12-31T00:00:00+00:00"
    assert doc["author"] == "Ada"
    assert doc["organization"] == "Example Org"
