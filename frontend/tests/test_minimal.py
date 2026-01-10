"""Minimal test without fixtures to debug pytest."""


def test_simple():
    """Most basic test possible."""
    assert 1 + 1 == 2


def test_import_shared():
    """Test importing shared package."""
    from shared.core.config import settings

    assert settings is not None


def test_import_frontend():
    """Test importing frontend package."""
    from frontend.api.main import app

    assert app is not None
