"""Pytest configuration for Indexer service tests."""

import os
import sys
from pathlib import Path

# Set ENVIRONMENT before importing any modules that use infrastructure_config
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("INDEXER_API_KEY", "test-api-key")

# Add indexer/src and shared/src to path for imports
indexer_root = Path(__file__).parent.parent
sys.path.insert(0, str(indexer_root / "src"))
sys.path.insert(0, str(indexer_root.parent / "shared" / "src"))

import gc  # noqa: E402
import time  # noqa: E402
import pytest  # noqa: E402
from unittest.mock import patch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared.db.search import ensure_db  # noqa: E402

# Test database path
TEST_DB_PATH = "test_indexer.db"


@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup test environment with clean database."""
    # 1. Setup Test DB with retry logic
    if os.path.exists(TEST_DB_PATH):
        gc.collect()
        for attempt in range(3):
            try:
                os.remove(TEST_DB_PATH)
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.2 * (attempt + 1))
                    gc.collect()

    ensure_db(TEST_DB_PATH)

    # Patch settings.DB_PATH
    with patch("app.core.config.settings.DB_PATH", TEST_DB_PATH):
        # Also patch the instantiated indexer_service's db_path
        from app.services.indexer import indexer_service

        original_indexer_path = indexer_service.db_path
        indexer_service.db_path = TEST_DB_PATH

        yield

        indexer_service.db_path = original_indexer_path

    # Cleanup with retry
    if os.path.exists(TEST_DB_PATH):
        gc.collect()
        for attempt in range(3):
            try:
                os.remove(TEST_DB_PATH)
                break
            except (PermissionError, OSError):
                if attempt < 2:
                    time.sleep(0.1)


@pytest.fixture
def test_client():
    """Create FastAPI TestClient for the Indexer app."""
    from app.main import app

    return TestClient(app)
