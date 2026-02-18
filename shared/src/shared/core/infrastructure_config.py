"""
Infrastructure Configuration

Base configuration for infrastructure-level settings shared across all services.
Contains database and path configurations.
"""

import os
from enum import Enum
from pathlib import Path


class Environment(str, Enum):
    """Application environment"""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


def _get_environment() -> Environment:
    """Get and validate ENVIRONMENT variable."""
    env_value = os.getenv("ENVIRONMENT")
    if env_value is None:
        raise RuntimeError(
            "ENVIRONMENT is required. Set to 'production', 'development', or 'test'."
        )
    try:
        return Environment(env_value.lower())
    except ValueError:
        raise RuntimeError(
            f"Invalid ENVIRONMENT value: '{env_value}'. "
            "Must be 'production', 'development', or 'test'."
        )


class InfrastructureSettings:
    """Infrastructure-level configuration (database, paths)"""

    # Database
    # PostgreSQL (production): Set DATABASE_URL environment variable
    # SQLite (test): Uses SEARCH_DB env var or default path
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    DB_PATH: str = os.getenv(
        "SEARCH_DB",
        str(
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "search.db"
        ),
    )

    # Environment
    ENVIRONMENT: Environment = _get_environment()


settings = InfrastructureSettings()
