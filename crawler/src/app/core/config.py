"""
Crawler Service Configuration

Configuration specific to the Crawler service, including crawl parameters
and indexer API configuration.
"""

import os
from shared.core.infrastructure_config import Environment, InfrastructureSettings


class CrawlerSettings(InfrastructureSettings):
    """Crawler service configuration (inherits infrastructure settings)"""

    # Application
    APP_NAME: str = "Crawler Service"
    APP_VERSION: str = "3.0.0"

    # Database Path (for UrlStore, Seeds)
    CRAWLER_DB_PATH: str = os.getenv("CRAWLER_DB_PATH", "/data/crawler.db")

    # Recrawl settings
    CRAWL_RECRAWL_AFTER_DAYS: int = int(os.getenv("CRAWL_RECRAWL_AFTER_DAYS", "30"))

    # Crawler Behavior
    CRAWL_USER_AGENT: str = os.getenv(
        "CRAWL_USER_AGENT", "SearchBot/0.3 (+https://example.local/; async crawler)"
    )
    CRAWL_TIMEOUT_SEC: int = int(os.getenv("CRAWL_TIMEOUT_SEC", "10"))
    CRAWL_OUTLINKS_PER_PAGE: int = int(os.getenv("CRAWL_OUTLINKS_PER_PAGE", "50"))
    CRAWL_CONCURRENCY: int = int(os.getenv("CRAWL_CONCURRENCY", "10"))
    CRAWL_WORKERS: int = int(os.getenv("CRAWL_WORKERS", "3"))
    CRAWL_SEEDS: list[str] = [
        s.strip() for s in os.getenv("CRAWL_SEEDS", "").split() if s.strip()
    ]

    # Indexer API (for submitting crawled pages)
    INDEXER_API_URL: str = os.getenv(
        "INDEXER_API_URL", "http://localhost:8000/api/v1/indexer/page"
    )
    INDEXER_API_KEY: str | None = os.getenv("INDEXER_API_KEY")  # Required outside tests


settings = CrawlerSettings()


def _validate_required(settings: CrawlerSettings) -> None:
    """Validate required settings outside of tests."""
    if settings.ENVIRONMENT == Environment.TEST:
        return

    if not settings.INDEXER_API_KEY:
        raise RuntimeError("Missing required environment variable: INDEXER_API_KEY")


_validate_required(settings)
