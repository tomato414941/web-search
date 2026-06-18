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
        "fetch_documents_for_opensearch_after_url",
        staticmethod(
            lambda *, limit, last_url: (
                [
                    (
                        "https://example.com/post",
                        "Example Title",
                        "Example content with facts.",
                    )
                ]
                if last_url is None
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


def test_rebuild_search_projection_can_run_segment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")

    class FakeClient:
        pass

    calls = []
    indexed_docs = []

    monkeypatch.setattr(
        rebuild_search_projection, "get_client", lambda url: FakeClient()
    )
    monkeypatch.setattr(rebuild_search_projection, "ensure_index", lambda client: None)
    monkeypatch.setattr(
        rebuild_search_projection.DocumentRepository,
        "count_documents",
        staticmethod(lambda: 10),
    )

    def fake_fetch(*, limit, last_url):
        calls.append((limit, last_url))
        if last_url == "https://example.com/start":
            return [
                ("https://example.com/a", "A", "content"),
                ("https://example.com/b", "B", "content"),
            ]
        return []

    monkeypatch.setattr(
        rebuild_search_projection.DocumentRepository,
        "fetch_documents_for_opensearch_after_url",
        staticmethod(fake_fetch),
    )
    monkeypatch.setattr(
        rebuild_search_projection.DocumentRepository,
        "fetch_link_rank_map",
        staticmethod(lambda urls: {}),
    )
    monkeypatch.setattr(
        rebuild_search_projection,
        "bulk_index",
        lambda client, docs: indexed_docs.extend(docs) or len(docs),
    )

    rebuild_search_projection.rebuild_search_projection(
        batch_size=10,
        opensearch_url="http://opensearch",
        start_after_url="https://example.com/start",
        max_documents=2,
    )

    assert calls == [(2, "https://example.com/start")]
    assert [doc["url"] for doc in indexed_docs] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
