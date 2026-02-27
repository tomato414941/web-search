"""
Indexer Service Configuration

Configuration specific to the Indexer service, including OpenAI API settings
and database configuration.
"""

from shared.core.infrastructure_config import Environment, InfrastructureSettings


class IndexerSettings(InfrastructureSettings):
    """Indexer service configuration (inherits infrastructure settings)"""

    # Application
    APP_NAME: str = "Indexer Service"
    APP_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Security (required - no default for security)
    INDEXER_API_KEY: str | None = None

    # OpenAI Embeddings
    OPENAI_API_KEY: str = ""
    OPENAI_EMBED_TIMEOUT_SEC: int = 30

    # Async index job worker
    INDEXER_JOB_WORKERS: int = 4
    INDEXER_JOB_BATCH_SIZE: int = 20
    INDEXER_JOB_LEASE_SEC: int = 120
    INDEXER_JOB_MAX_RETRIES: int = 5
    INDEXER_JOB_POLL_INTERVAL_MS: int = 200
    INDEXER_JOB_RETRY_BASE_SEC: int = 5
    INDEXER_JOB_RETRY_MAX_SEC: int = 1800
    INDEXER_JOB_CONCURRENCY: int = 5

    # PageRank scheduling
    PAGERANK_INTERVAL_HOURS: int = 24
    DOMAIN_RANK_INTERVAL_HOURS: int = 6


settings = IndexerSettings()


def _validate_required(settings: IndexerSettings) -> None:
    """Validate required settings outside of tests."""
    if settings.ENVIRONMENT == Environment.TEST:
        return

    if not settings.INDEXER_API_KEY:
        raise RuntimeError("Missing required environment variable: INDEXER_API_KEY")


_validate_required(settings)
