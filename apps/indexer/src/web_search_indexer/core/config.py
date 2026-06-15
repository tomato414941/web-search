"""
Indexer Service Configuration

Configuration specific to the Indexer service, including OpenAI API settings
and database configuration.
"""

from web_search_core.infrastructure_config import Environment, InfrastructureSettings


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

    # OpenSearch
    OPENSEARCH_URL: str = "http://opensearch:9200"
    OPENSEARCH_ENABLED: bool = False


settings = IndexerSettings()


def _validate_required(settings: IndexerSettings) -> None:
    """Validate required settings outside of tests."""
    if settings.ENVIRONMENT == Environment.TEST:
        return

    if not settings.INDEXER_API_KEY:
        raise RuntimeError("Missing required environment variable: INDEXER_API_KEY")


_validate_required(settings)
