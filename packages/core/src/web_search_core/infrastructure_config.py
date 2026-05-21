"""
Infrastructure Configuration

Base configuration for infrastructure-level settings shared across all services.
Uses pydantic-settings for automatic environment variable loading and type coercion.
"""

from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment"""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


class InfrastructureSettings(BaseSettings):
    """Infrastructure-level configuration (database, paths)"""

    model_config = SettingsConfigDict(extra="ignore")

    # Database
    DATABASE_URL: str

    # Environment
    ENVIRONMENT: Environment

    # Run Alembic migrations on service startup (for local dev without db-migrate)
    RUN_MIGRATIONS: bool = False


settings = InfrastructureSettings()
