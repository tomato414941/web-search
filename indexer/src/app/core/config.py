"""
Indexer Service Configuration

Configuration specific to the Indexer service, including OpenAI API settings
and database configuration.
"""

import os
from shared.core.infrastructure_config import InfrastructureSettings


class IndexerSettings(InfrastructureSettings):
    """Indexer service configuration (inherits infrastructure settings)"""

    # Application
    APP_NAME: str = "Indexer Service"
    APP_VERSION: str = "1.0.0"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Security
    INDEXER_API_KEY: str = os.getenv("INDEXER_API_KEY", "dev-key")

    # OpenAI Embeddings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")


settings = IndexerSettings()
