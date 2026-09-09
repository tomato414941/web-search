"""
Frontend Configuration

Service-specific configuration for the Frontend service.
Inherits infrastructure settings from the shared core package.
"""

from web_search_core.infrastructure_config import InfrastructureSettings


class Settings(InfrastructureSettings):
    """Frontend service configuration"""

    # Crawler Service Integration
    CRAWLER_SERVICE_URL: str = "http://localhost:8000"

    # Search Settings
    MAX_QUERY_LEN: int = 200
    MAX_PAGE: int = 100
    MAX_PER_PAGE: int = 50
    RESULTS_LIMIT: int = 10
    HYBRID_SEARCH_TIMEOUT_SEC: float = 3.0
    MAX_PER_DOMAIN: int = 5
    DIVERSITY_OVERSCAN: int = 5

    # Analytics
    ANALYTICS_SALT: str = ""

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


settings = Settings()
