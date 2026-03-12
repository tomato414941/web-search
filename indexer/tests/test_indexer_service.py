from unittest.mock import MagicMock

from app.services import indexer as indexer_module


def test_index_to_opensearch_includes_url_metadata(monkeypatch):
    service = indexer_module.IndexerService(db_path="test")
    client = MagicMock()
    captured = {}

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)
    monkeypatch.setattr(
        indexer_module,
        "compute_content_quality",
        lambda *args, **kwargs: 0.1,
    )
    monkeypatch.setattr(
        indexer_module,
        "compute_temporal_anchor",
        lambda *args, **kwargs: 0.2,
    )
    monkeypatch.setattr(
        indexer_module,
        "compute_authorship_clarity",
        lambda *args, **kwargs: 0.3,
    )
    monkeypatch.setattr(service, "_get_origin_score", lambda url: (0.4, "river"))
    monkeypatch.setattr(service, "_get_authority", lambda url: 0.5)

    def fake_index_document(*args, **kwargs):
        captured.update(kwargs)

    import shared.opensearch.client as opensearch_client
    import shared.search_kernel.factual_density as factual_density_module

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    monkeypatch.setattr(
        factual_density_module,
        "compute_factual_density",
        lambda *args, **kwargs: 0.6,
    )

    service._index_to_opensearch(
        url="https://github.com/",
        title="GitHub",
        content="GitHub builds software together.",
        outlinks_count=3,
    )

    assert captured["host"] == "github.com"
    assert captured["path"] == "/"
    assert captured["is_homepage"] is True


def test_index_to_opensearch_skips_excluded_hosts(monkeypatch):
    service = indexer_module.IndexerService(db_path="test")
    client = MagicMock()

    monkeypatch.setattr(indexer_module, "_get_opensearch_client", lambda: client)
    monkeypatch.setattr(
        indexer_module,
        "compute_content_quality",
        lambda *args, **kwargs: 0.1,
    )
    monkeypatch.setattr(
        indexer_module,
        "compute_temporal_anchor",
        lambda *args, **kwargs: 0.2,
    )
    monkeypatch.setattr(
        indexer_module,
        "compute_authorship_clarity",
        lambda *args, **kwargs: 0.3,
    )
    monkeypatch.setattr(service, "_get_origin_score", lambda url: (0.4, "river"))
    monkeypatch.setattr(service, "_get_authority", lambda url: 0.5)

    called = {"indexed": False, "deleted": False}

    def fake_index_document(*args, **kwargs):
        called["indexed"] = True

    def fake_delete_document(*args, **kwargs):
        called["deleted"] = True

    import shared.opensearch.client as opensearch_client
    import shared.search_kernel.factual_density as factual_density_module

    monkeypatch.setattr(opensearch_client, "index_document", fake_index_document)
    monkeypatch.setattr(opensearch_client, "delete_document", fake_delete_document)
    monkeypatch.setattr(
        factual_density_module,
        "compute_factual_density",
        lambda *args, **kwargs: 0.6,
    )

    service._index_to_opensearch(
        url="https://accounts.hatena.ne.jp/login",
        title="Login",
        content="Login page",
        outlinks_count=0,
    )

    assert called["deleted"] is True
    assert called["indexed"] is False
