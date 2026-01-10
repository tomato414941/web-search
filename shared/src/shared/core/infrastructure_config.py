"""
Infrastructure Configuration

Base configuration for infrastructure-level settings shared across all services.
Contains only database, Redis, and path configurations.
"""
import os
from pathlib import Path


class InfrastructureSettings:
    """Infrastructure-level configuration (database, Redis, paths)"""
    
    # Project Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    
    # Database
    DB_PATH: str = os.getenv("SEARCH_DB", str(DATA_DIR / "search.db"))
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


settings = InfrastructureSettings()
