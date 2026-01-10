"""
Frontend Configuration

Service-specific configuration for the Frontend service.
Inherits infrastructure settings from shared library.
"""
import os

from shared.core.infrastructure_config import InfrastructureSettings


class Settings(InfrastructureSettings):
    """Frontend service configuration"""

    # Admin Authentication
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
    SECRET_KEY: str = os.getenv("ADMIN_SESSION_SECRET", "change-me-in-production")

    # Crawler Service Integration
    CRAWLER_SERVICE_URL: str = os.getenv("CRAWLER_SERVICE_URL", "http://localhost:8000")

    # Crawler Queue Keys (for stats display)
    CRAWL_QUEUE_KEY: str = os.getenv("CRAWL_QUEUE_KEY", "crawl:queue")
    CRAWL_SEEN_KEY: str = os.getenv("CRAWL_SEEN_KEY", "crawl:seen")

    # Search Settings
    MAX_QUERY_LEN: int = int(os.getenv("MAX_QUERY_LEN", "200"))
    MAX_PAGE: int = int(os.getenv("MAX_PAGE", "100"))
    MAX_PER_PAGE: int = int(os.getenv("MAX_PER_PAGE", "50"))
    RESULTS_LIMIT: int = int(os.getenv("RESULTS_LIMIT", "10"))

    # Indexer API
    INDEXER_API_KEY: str = os.getenv("INDEXER_API_KEY", "dev-key")

    # OpenAI (for embeddings)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Security
    ALLOWED_HOSTS: list[str] = os.getenv("ALLOWED_HOSTS", "*").split(",")
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8080"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"


settings = Settings()
