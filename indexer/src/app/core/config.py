"""
Indexer Service Configuration

Configuration specific to the Indexer service, including OpenAI API settings
and database configuration.
"""

import os
from shared.core.infrastructure_config import Environment, InfrastructureSettings


class IndexerSettings(InfrastructureSettings):
    """Indexer service configuration (inherits infrastructure settings)"""

    # Application
    APP_NAME: str = "Indexer Service"
    APP_VERSION: str = "1.0.0"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Security (required - no default for security)
    INDEXER_API_KEY: str | None = os.getenv("INDEXER_API_KEY")

    # OpenAI Embeddings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_EMBED_TIMEOUT_SEC: int = int(os.getenv("OPENAI_EMBED_TIMEOUT_SEC", "30"))

    # Async index job worker
    INDEXER_JOB_WORKERS: int = int(os.getenv("INDEXER_JOB_WORKERS", "4"))
    INDEXER_JOB_BATCH_SIZE: int = int(os.getenv("INDEXER_JOB_BATCH_SIZE", "20"))
    INDEXER_JOB_LEASE_SEC: int = int(os.getenv("INDEXER_JOB_LEASE_SEC", "120"))
    INDEXER_JOB_MAX_RETRIES: int = int(os.getenv("INDEXER_JOB_MAX_RETRIES", "5"))
    INDEXER_JOB_POLL_INTERVAL_MS: int = int(
        os.getenv("INDEXER_JOB_POLL_INTERVAL_MS", "200")
    )
    INDEXER_JOB_RETRY_BASE_SEC: int = int(os.getenv("INDEXER_JOB_RETRY_BASE_SEC", "5"))
    INDEXER_JOB_RETRY_MAX_SEC: int = int(os.getenv("INDEXER_JOB_RETRY_MAX_SEC", "1800"))

    # PageRank scheduling
    PAGERANK_INTERVAL_HOURS: int = int(os.getenv("PAGERANK_INTERVAL_HOURS", "24"))
    DOMAIN_RANK_INTERVAL_HOURS: int = int(os.getenv("DOMAIN_RANK_INTERVAL_HOURS", "6"))


settings = IndexerSettings()


def _validate_required(settings: IndexerSettings) -> None:
    """Validate required settings outside of tests."""
    if settings.ENVIRONMENT == Environment.TEST:
        return

    if not settings.INDEXER_API_KEY:
        raise RuntimeError("Missing required environment variable: INDEXER_API_KEY")


_validate_required(settings)
