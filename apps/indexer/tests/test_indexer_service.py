from unittest.mock import MagicMock
from types import SimpleNamespace
import pytest

from web_search_indexer.services import indexer as indexer_module
from web_search_indexer.services import opensearch_document


def test_index_to_opensearch_includes_url_metadata(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()
    captured = {}

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)

    def fake_index_document(client, document):
        captured.update(document)

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    service._index_to_opensearch_page(
        indexer_module.IndexedPage(
            url="https://github.com/",
            title="GitHub",
            content="GitHub builds software together.",
        )
    )

    assert captured["host"] == "github.com"
    assert len(captured["embedding"]) == 1024
    assert captured["path"] == "/"
    assert "is_homepage" not in captured


def test_build_search_index_document_uses_search_field_names(monkeypatch):
    page = indexer_module.IndexedPage(
        url="https://github.com/",
        title="GitHub",
        content="GitHub builds software together.",
    )

    doc = opensearch_document.build_search_index_document(
        page,
    )

    assert doc is not None
    assert doc["title"] == "GitHub"
    assert doc["content"] == "GitHub builds software together."
    assert doc["title_terms"] == "github"
    assert doc["content_terms"] == "github builds software together."
    assert "title_tokens" not in doc
    assert "content_tokens" not in doc
    assert "is_homepage" not in doc
    assert "indexed_at" not in doc


def test_build_search_index_document_bounds_content_projection(monkeypatch):
    page = indexer_module.IndexedPage(
        url="https://example.com/",
        title="Example",
        content="a" * (opensearch_document.SEARCH_CONTENT_MAX_CHARS + 1),
    )

    doc = opensearch_document.build_search_index_document(
        page,
    )

    assert doc is not None
    assert len(doc["content"]) == opensearch_document.SEARCH_CONTENT_MAX_CHARS
    assert doc["content_terms"] == "a" * opensearch_document.SEARCH_CONTENT_MAX_CHARS


def test_index_to_opensearch_skips_excluded_hosts(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)

    called = {"indexed": False, "deleted": False}

    def fake_index_document(*args, **kwargs):
        called["indexed"] = True

    def fake_delete_document(*args, **kwargs):
        called["deleted"] = True

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    monkeypatch.setattr(opensearch_client, "delete_document", fake_delete_document)
    service._index_to_opensearch_page(
        indexer_module.IndexedPage(
            url="https://accounts.hatena.ne.jp/login",
            title="Login",
            content="Login page",
        )
    )

    assert called["deleted"] is True
    assert called["indexed"] is False


def test_index_to_opensearch_skips_excluded_paths(monkeypatch):
    service = indexer_module.IndexerService()
    client = MagicMock()

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)

    called = {"indexed": False, "deleted": False}

    def fake_index_document(*args, **kwargs):
        called["indexed"] = True

    def fake_delete_document(*args, **kwargs):
        called["deleted"] = True

    import web_search_opensearch.client as opensearch_client

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    monkeypatch.setattr(opensearch_client, "delete_document", fake_delete_document)
    service._index_to_opensearch_page(
        indexer_module.IndexedPage(
            url="https://example.com/login/reset",
            title="Login",
            content="Login page",
        )
    )

    assert called["deleted"] is True
    assert called["indexed"] is False


def test_single_document_projection_failure_is_not_success(monkeypatch):
    service = indexer_module.IndexerService()
    monkeypatch.setattr(
        service,
        "_build_search_index_document",
        lambda page: (_ for _ in ()).throw(RuntimeError("embed failed")),
    )
    with pytest.raises(indexer_module.OpenSearchIndexingError):
        service._index_to_opensearch_page(
            indexer_module.IndexedPage("https://example.com/", "Example", "Content")
        )


def test_excluded_document_does_not_generate_embeddings(monkeypatch):
    def unexpected():
        raise AssertionError("Excluded documents must not call embeddings API")

    monkeypatch.setattr(opensearch_document, "get_embeddings", unexpected)
    page = indexer_module.IndexedPage("https://example.com/login", "Login", "Sign in")
    assert opensearch_document.build_search_index_document(page) is None


def test_batch_projection_preserves_document_vector_alignment(monkeypatch):
    inputs = []

    def embed(texts):
        inputs.append(texts)
        return [[1.0], [2.0]]

    monkeypatch.setattr(
        opensearch_document, "get_embeddings", lambda: SimpleNamespace(embed=embed)
    )
    pages = [
        indexer_module.IndexedPage("https://example.com/a", "A", "First"),
        indexer_module.IndexedPage("https://example.com/login", "Login", "Sign in"),
        indexer_module.IndexedPage("https://example.com/empty", "", " "),
        indexer_module.IndexedPage("https://example.com/b", "B", "Second"),
    ]

    documents = opensearch_document.build_search_index_documents(pages)

    assert inputs == [["A\nFirst", "B\nSecond"]]
    assert [(doc["url"], doc["embedding"]) for doc in documents] == [
        ("https://example.com/a", [1.0]),
        ("https://example.com/b", [2.0]),
    ]
