"""Native RRF integration, using deterministic vectors rather than a quality benchmark."""

import json
import os
import random
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from opensearchpy import OpenSearch
from testcontainers.core.container import DockerContainer

from web_search_opensearch.client import bulk_index
from web_search_opensearch.embeddings import DIMENSIONS
from web_search_opensearch.mapping import ensure_index, validate_index
from web_search_engine import SearchEngine


@pytest.fixture(scope="module")
def opensearch():
    external_url = os.environ.get("TEST_OPENSEARCH_URL")
    container = None
    client = None
    try:
        if not external_url:
            container = (
                DockerContainer("opensearchproject/opensearch:2.19.6")
                .with_exposed_ports(9200)
                .with_env("discovery.type", "single-node")
                .with_env("cluster.routing.allocation.disk.threshold_enabled", "false")
                .with_env("DISABLE_INSTALL_DEMO_CONFIG", "true")
                .with_env("DISABLE_SECURITY_PLUGIN", "true")
                .with_env("OPENSEARCH_JAVA_OPTS", "-Xms512m -Xmx512m")
                .with_kwargs(mem_limit="2g")
            )
            container.start()
            external_url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9200)}"
        client = OpenSearch(hosts=[external_url], timeout=5)
        deadline = time.monotonic() + 120
        while not client.ping():
            if time.monotonic() > deadline:
                raise RuntimeError("Test OpenSearch did not start")
            time.sleep(1)
        yield client
    finally:
        if client:
            client.close()
        if container:
            container.stop()


@pytest.fixture
def hybrid_index(opensearch):
    name = f"hybrid-test-{uuid4().hex}"
    try:
        ensure_index(opensearch, target_index=name)
        validate_index(opensearch, target_index=name)
        yield name
    finally:
        opensearch.indices.delete(index=name, ignore=[404])


def vector(x, y=0):
    return [float(x), float(y)] + [0.0] * (DIMENSIONS - 2)


def document(url, title, embedding):
    from urllib.parse import urlsplit

    return {
        "url": url,
        "title": title,
        "content": title,
        "title_terms": title,
        "content_terms": title,
        "host": urlsplit(url).hostname,
        "path": urlsplit(url).path or "/",
        "embedding": embedding,
    }


def test_native_rrf_retains_both_branches_and_stable_pages(opensearch, hybrid_index):
    rng = random.Random(42)
    docs = [
        document("https://example.com/lexical", "needle", vector(-1)),
        document("https://example.com/semantic", "different words", vector(1)),
        *[
            document(
                f"https://example.com/noise-{i}",
                f"other text {i}",
                [rng.uniform(-1, 1) for _ in range(DIMENSIONS)],
            )
            for i in range(210)
        ],
    ]
    assert bulk_index(opensearch, docs, target_index=hybrid_index) == len(docs)
    opensearch.indices.refresh(index=hybrid_index)
    engine = SearchEngine(opensearch, lambda text: vector(1), index=hybrid_index)
    first = engine.search("needle", 10, 1)
    second = engine.search("needle", 10, 2)
    combined = engine.search("needle", 20, 1)
    urls = [hit.url for hit in first.hits]
    assert "https://example.com/lexical" in urls
    assert "https://example.com/semantic" in urls
    assert urls + [hit.url for hit in second.hits] == [hit.url for hit in combined.hits]
    assert len(set(urls + [hit.url for hit in second.hits])) == 20
    assert first.total == 200
    assert first.last_page == 20


def test_operators_constrain_both_branches(opensearch, hybrid_index):
    titles = {
        "https://example.com/allowed": "needle required phrase",
        "https://sub.example.com/allowed": "required phrase",
        "https://notexample.com/wrong-host": "needle required phrase",
        "https://example.com/banned": "needle required phrase forbidden",
        "https://example.com/wrong-phrase": "needle unrelated text",
    }
    docs = [document(url, title, vector(1)) for url, title in titles.items()]
    bulk_index(opensearch, docs, target_index=hybrid_index)
    opensearch.indices.refresh(index=hybrid_index)
    result = SearchEngine(
        opensearch, lambda text: vector(1), index=hybrid_index
    ).search('needle "required phrase" site:example.com -forbidden')
    assert {hit.url for hit in result.hits} == {
        "https://example.com/allowed",
        "https://sub.example.com/allowed",
    }


def test_ingestion_rebuild_and_public_api(
    opensearch, hybrid_index, monkeypatch, tmp_path
):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("INDEXER_API_KEY", "test-api-key")
    from web_search_core.testing import ensure_test_pg

    ensure_test_pg()
    from web_search_postgres.migrate import migrate

    migrate()
    from fastapi.testclient import TestClient
    from web_search_indexer.main import app as indexer_app
    from web_search_indexer.services import indexer, opensearch_document
    from web_search_indexer.cli import rebuild_search_projection
    from web_search_frontend.api.main import app as frontend_app
    from web_search_frontend.services.search import search_service

    monkeypatch.setenv("OPENSEARCH_INDEX_NAME", hybrid_index)
    monkeypatch.setattr(indexer, "_get_opensearch_client", lambda: opensearch)
    monkeypatch.setattr(
        opensearch_document,
        "get_embeddings",
        lambda: SimpleNamespace(embed=lambda texts: [vector(1) for _ in texts]),
    )
    monkeypatch.setattr(rebuild_search_projection, "get_client", lambda url: opensearch)
    monkeypatch.setattr(
        search_service,
        "_engine",
        SearchEngine(opensearch, lambda text: vector(1), index=hybrid_index),
    )

    url = f"https://example.com/native-{uuid4().hex}"
    with TestClient(indexer_app) as writer, TestClient(frontend_app) as reader:
        response = writer.post(
            "/documents",
            headers={"X-API-Key": "test-api-key"},
            json={
                "url": url,
                "title": "needle 日本語",
                "content": "保存された本文です。",
            },
        )
        assert response.status_code == 200, response.text
        opensearch.indices.refresh(index=hybrid_index)
        response = reader.get(
            "/search-results", params={"q": "needle", "include_content": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == "hybrid"
        assert response.json()["hits"][0]["url"] == url
        assert response.json()["hits"][0]["content"] == "保存された本文です。"
        assert (
            reader.get("/indexed-documents/by-url", params={"url": url}).json()[
                "content"
            ]
            == "保存された本文です。"
        )
        assert (
            reader.get(
                "/search-results", params={"q": "needle", "mode": "bm25"}
            ).status_code
            == 422
        )
        opensearch.delete(index=hybrid_index, id=url, refresh=True)
        checkpoint = tmp_path / "projection.json"
        rebuild_search_projection.rebuild_search_projection(
            index_name=hybrid_index, checkpoint_file=checkpoint
        )
        assert json.loads(checkpoint.read_text())["progress"]["complete"] is True
        opensearch.indices.refresh(index=hybrid_index)
        assert reader.get("/search-results?q=needle").json()["hits"][0]["url"] == url

        def fail_embedding(text):
            raise RuntimeError("embedding provider unavailable")

        monkeypatch.setattr(
            search_service,
            "_engine",
            SearchEngine(opensearch, fail_embedding, index=hybrid_index),
        )
        assert reader.get("/search-results?q=needle").status_code == 503
        assert reader.get("/?q=needle").status_code == 503
