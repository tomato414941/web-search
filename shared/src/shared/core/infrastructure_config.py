"""
Infrastructure Configuration

Base configuration for infrastructure-level settings shared across all services.
Uses pydantic-settings for automatic environment variable loading and type coercion.
"""

from enum import Enum
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment"""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


_DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "search.db"
)


class InfrastructureSettings(BaseSettings):
    """Infrastructure-level configuration (database, paths)"""

    model_config = SettingsConfigDict(extra="ignore")

    # Database
    # PostgreSQL (production): Set DATABASE_URL environment variable
    # SQLite (test): Uses SEARCH_DB env var or default path
    DATABASE_URL: str | None = None
    DB_PATH: str = Field(
        default=_DEFAULT_DB_PATH,
        validation_alias=AliasChoices("SEARCH_DB", "DB_PATH"),
    )

    # Environment
    ENVIRONMENT: Environment

    # Run Alembic migrations on service startup (for local dev without db-migrate)
    RUN_MIGRATIONS: bool = False


settings = InfrastructureSettings()
