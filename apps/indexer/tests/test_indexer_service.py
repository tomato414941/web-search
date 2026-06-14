from unittest.mock import MagicMock
import pytest

from web_search_indexer.services import indexer as indexer_module
from web_search_indexer.services import opensearch_document


def test_index_to_opensearch_includes_url_metadata(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()
    captured = {}

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)
    monkeypatch.setattr(service, "_get_link_ranks", lambda url: (0.5, 0.25))

    def fake_index_document(*args, **kwargs):
        captured.update(kwargs)

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    service._index_to_opensearch(
        url="https://github.com/",
        title="GitHub",
        content="GitHub builds software together.",
        outlinks_count=3,
    )

    assert captured["host"] == "github.com"
    assert captured["page_rank"] == 0.5
    assert captured["domain_rank"] == 0.25
    assert captured["path"] == "/"
    assert captured["is_homepage"] is True


def test_build_opensearch_document_uses_search_field_names(monkeypatch):
    page = indexer_module.IndexedPage(
        url="https://github.com/",
        title="GitHub",
        content="GitHub builds software together.",
        outlinks_count=3,
    )

    doc = opensearch_document.build_opensearch_document(
        page,
        page_rank=0.5,
        domain_rank=0.25,
        indexed_at="2026-05-20T00:00:00+00:00",
    )

    assert doc is not None
    assert doc["title"] == "github"
    assert doc["content"] == "github builds software together."
    assert "title_tokens" not in doc
    assert "content_tokens" not in doc


def test_index_to_opensearch_skips_excluded_hosts(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)
    monkeypatch.setattr(service, "_get_link_ranks", lambda url: (0.5, 0.25))

    called = {"indexed": False, "deleted": False}

    def fake_index_document(*args, **kwargs):
        called["indexed"] = True

    def fake_delete_document(*args, **kwargs):
        called["deleted"] = True

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    monkeypatch.setattr(opensearch_client, "delete_document", fake_delete_document)
    service._index_to_opensearch(
        url="https://accounts.hatena.ne.jp/login",
        title="Login",
        content="Login page",
        outlinks_count=0,
    )

    assert called["deleted"] is True
    assert called["indexed"] is False


def test_index_to_opensearch_skips_excluded_paths(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)
    monkeypatch.setattr(service, "_get_link_ranks", lambda url: (0.5, 0.25))

    called = {"indexed": False, "deleted": False}

    def fake_index_document(*args, **kwargs):
        called["indexed"] = True

    def fake_delete_document(*args, **kwargs):
        called["deleted"] = True

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    monkeypatch.setattr(opensearch_client, "delete_document", fake_delete_document)
    service._index_to_opensearch(
        url="https://example.com/login/reset",
        title="Login",
        content="Login page",
        outlinks_count=0,
    )

    assert called["deleted"] is True
    assert called["indexed"] is False


def test_batch_opensearch_raises_on_partial_bulk(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)
    monkeypatch.setattr(
        service,
        "_build_opensearch_document",
        lambda page: {"url": page.url},
    )

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "bulk_index", lambda client, docs: 0)

    page = indexer_module.IndexedPage(
        url="https://example.com/missing",
        title="Title",
        content="Body",
        outlinks_count=0,
    )

    with pytest.raises(indexer_module.OpenSearchIndexingError):
        service._index_pages_to_opensearch_sync([page])
