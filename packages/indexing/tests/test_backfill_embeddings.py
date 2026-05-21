import pytest

from web_search_indexing import backfill_embeddings


def test_backfill_requires_explicit_embedding_opt_in(monkeypatch):
    monkeypatch.delenv("EMBEDDING_ENRICHMENT_ENABLED", raising=False)

    with pytest.raises(SystemExit) as exc:
        backfill_embeddings.backfill(dry_run=True)

    assert exc.value.code == 1


def test_backfill_dry_run_stops_before_openai_client(monkeypatch):
    monkeypatch.setenv("EMBEDDING_ENRICHMENT_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(backfill_embeddings, "_ensure_embedding_schema", lambda: None)
    monkeypatch.setattr(
        backfill_embeddings,
        "_count_documents_without_embeddings",
        lambda: 2,
    )
    monkeypatch.setattr(
        backfill_embeddings,
        "OpenAI",
        lambda api_key: (_ for _ in ()).throw(
            AssertionError("OpenAI client should not be created during dry-run")
        ),
    )

    backfill_embeddings.backfill(dry_run=True)
