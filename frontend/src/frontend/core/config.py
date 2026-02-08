"""
Frontend Configuration

Service-specific configuration for the Frontend service.
Inherits infrastructure settings from shared library.
"""

import os

from shared.core.infrastructure_config import Environment, InfrastructureSettings


class Settings(InfrastructureSettings):
    """Frontend service configuration"""

    # Admin Authentication (required - no defaults for security)
    ADMIN_USERNAME: str | None = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD: str | None = os.getenv("ADMIN_PASSWORD")
    SECRET_KEY: str | None = os.getenv("ADMIN_SESSION_SECRET")

    # Crawler Service Integration
    CRAWLER_SERVICE_URL: str = os.getenv("CRAWLER_SERVICE_URL", "http://localhost:8000")

    @property
    def CRAWLER_INSTANCES(self) -> list[dict[str, str]]:
        """Parse CRAWLER_INSTANCES env var: 'name1|url1,name2|url2'"""
        raw = os.getenv("CRAWLER_INSTANCES", "")
        if not raw:
            return [{"name": "default", "url": self.CRAWLER_SERVICE_URL}]
        instances = []
        for item in raw.split(","):
            item = item.strip()
            if "|" in item:
                name, url = item.split("|", 1)
                instances.append({"name": name.strip(), "url": url.strip()})
        return (
            instances
            if instances
            else [{"name": "default", "url": self.CRAWLER_SERVICE_URL}]
        )

    # Search Settings
    MAX_QUERY_LEN: int = int(os.getenv("MAX_QUERY_LEN", "200"))
    MAX_PAGE: int = int(os.getenv("MAX_PAGE", "100"))
    MAX_PER_PAGE: int = int(os.getenv("MAX_PER_PAGE", "50"))
    RESULTS_LIMIT: int = int(os.getenv("RESULTS_LIMIT", "10"))

    # Indexer API (required - no default for security)
    INDEXER_API_KEY: str | None = os.getenv("INDEXER_API_KEY")

    # OpenAI (for embeddings)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Security
    ALLOWED_HOSTS: list[str] = os.getenv(
        "ALLOWED_HOSTS", "localhost,127.0.0.1,testclient,testserver"
    ).split(",")
    CORS_ORIGINS: list[str] = (
        os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
    )

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"


settings = Settings()


def _validate_required(settings: Settings) -> None:
    """Validate required settings outside of tests."""
    if settings.ENVIRONMENT == Environment.TEST:
        return

    required_fields = [
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "SECRET_KEY",
        "INDEXER_API_KEY",
    ]
    missing = [name for name in required_fields if not getattr(settings, name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )


_validate_required(settings)
