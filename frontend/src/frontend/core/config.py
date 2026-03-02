"""
Frontend Configuration

Service-specific configuration for the Frontend service.
Inherits infrastructure settings from shared library.
"""

import os

from pydantic import AliasChoices, Field

from shared.core.infrastructure_config import Environment, InfrastructureSettings


class Settings(InfrastructureSettings):
    """Frontend service configuration"""

    # Admin Authentication (required - no defaults for security)
    ADMIN_USERNAME: str | None = None
    ADMIN_PASSWORD: str | None = None
    SECRET_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADMIN_SESSION_SECRET", "SECRET_KEY"),
    )

    # Crawler Service Integration
    CRAWLER_SERVICE_URL: str = "http://localhost:8000"

    # Indexer Service Integration (Admin stats UI, internal-only in docker)
    INDEXER_SERVICE_URL: str = "http://localhost:8081"

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
    MAX_QUERY_LEN: int = 200
    MAX_PAGE: int = 100
    MAX_PER_PAGE: int = 50
    RESULTS_LIMIT: int = 10
    HYBRID_SEARCH_TIMEOUT_SEC: float = 3.0
    MAX_PER_DOMAIN: int = 3
    DIVERSITY_OVERSCAN: int = 5

    # Indexer API (required - no default for security)
    INDEXER_API_KEY: str | None = None

    # Public API Key Settings
    API_KEY_DAILY_LIMIT: int = 1000

    # OpenAI (for embeddings)
    OPENAI_API_KEY: str = ""

    # Analytics
    ANALYTICS_SALT: str = ""
    ANALYTICS_EXCLUDED_USER_AGENTS: str = "curl/"
    ANALYTICS_EXCLUDED_QUERIES: str = "deploy-check,bm25,sudachipy"

    # Security
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testclient,testserver"
    CORS_ORIGINS: str = ""

    # OpenSearch
    OPENSEARCH_URL: str = "http://opensearch:9200"
    OPENSEARCH_ENABLED: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    def get_allowed_hosts(self) -> list[str]:
        return [s.strip() for s in self.ALLOWED_HOSTS.split(",") if s.strip()]

    def get_cors_origins(self) -> list[str]:
        return [s.strip() for s in self.CORS_ORIGINS.split(",") if s.strip()]

    def get_excluded_user_agents(self) -> list[str]:
        return [
            s.strip()
            for s in self.ANALYTICS_EXCLUDED_USER_AGENTS.split(",")
            if s.strip()
        ]

    def get_excluded_queries(self) -> list[str]:
        return [
            s.strip() for s in self.ANALYTICS_EXCLUDED_QUERIES.split(",") if s.strip()
        ]


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
