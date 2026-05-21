"""
Crawler Service Configuration

Configuration specific to the Crawler service, including crawl parameters
and indexer API configuration.
"""

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator

from web_search_core.infrastructure_config import Environment, InfrastructureSettings

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class CrawlerSettings(InfrastructureSettings):
    """Crawler service configuration (inherits infrastructure settings)"""

    # Application
    APP_NAME: str = "Crawler Service"
    APP_VERSION: str = "3.0.0"

    # Database Path (for UrlStore, Seeds)
    CRAWLER_DB_PATH: str = "/data/crawler.db"

    # Auto-start crawl workers on service startup
    CRAWL_AUTO_START: bool = False
    ADMIN_CACHE_REFRESH_SEC: int = 60
    FRONTIER_MAINTENANCE_REFRESH_SEC: int = 60

    # Recrawl settings
    CRAWL_RECRAWL_AFTER_DAYS: int = 30

    # Crawler Behavior
    CRAWL_USER_AGENT: str = (
        "PaleblueBot/1.0 (+https://palebluesearch.com/about; web crawler)"
    )
    CRAWL_TIMEOUT_SEC: int = 5
    CRAWL_OUTLINKS_PER_PAGE: int = 50
    CRAWL_CONCURRENCY: int = 10
    CRAWL_SEEDS: list[str] = []

    # Frontier planner
    FRONTIER_PLANNER_BATCH_SIZE: int = Field(
        default=500,
        validation_alias=AliasChoices(
            "FRONTIER_PLANNER_BATCH_SIZE",
            "SCHEDULER_BATCH_SIZE",
        ),
    )
    FRONTIER_PLANNER_DOMAIN_MAX_CONCURRENT: int = Field(
        default=2,
        validation_alias=AliasChoices(
            "FRONTIER_PLANNER_DOMAIN_MAX_CONCURRENT",
            "SCHEDULER_DOMAIN_MAX_CONCURRENT",
        ),
    )
    FRONTIER_PLANNER_LEASE_SECONDS: int = Field(
        default=300,
        validation_alias=AliasChoices(
            "FRONTIER_PLANNER_LEASE_SECONDS",
            "SCHEDULER_LEASE_SECONDS",
        ),
    )

    # TCP / networking
    CRAWL_TCP_LIMIT: int = 50
    ROBOTS_CACHE_SIZE: int = 500000

    # Static crawler denylist file path
    CRAWL_DENYLIST_PATH: str = Field(
        default=str(_DATA_DIR / "crawl_denylist.yml"),
        validation_alias=AliasChoices("CRAWL_DENYLIST_PATH", "DOMAIN_BLOCKLIST_PATH"),
    )

    # URL pattern filters file path
    URL_FILTERS_PATH: str = str(_DATA_DIR / "url_filters.yml")
    URL_ADMISSION_RULES_PATH: str = str(_DATA_DIR / "url_admission_rules.yml")

    # Robots block filter (skip frontier admission for frequently blocked domains)
    CRAWL_ROBOTS_BLOCK_WINDOW_HOURS: int = 24
    CRAWL_ROBOTS_BLOCK_MIN_COUNT: int = 3

    # Indexer API (for submitting crawled pages)
    INDEXER_API_URL: str = "http://localhost:8000/api/v1/indexer/page"
    INDEXER_API_KEY: str | None = None  # Required outside tests

    @field_validator("CRAWL_SEEDS", mode="before")
    @classmethod
    def _parse_space_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [s.strip() for s in v.split() if s.strip()]
        return v


settings = CrawlerSettings()


def _validate_required(settings: CrawlerSettings) -> None:
    """Validate required settings outside of tests."""
    if settings.ENVIRONMENT == Environment.TEST:
        return

    if not settings.INDEXER_API_KEY:
        raise RuntimeError("Missing required environment variable: INDEXER_API_KEY")


_validate_required(settings)
