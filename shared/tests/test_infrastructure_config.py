"""Test infrastructure configuration."""

import os


class TestInfrastructureSettings:
    """Test InfrastructureSettings class."""

    def test_redis_url_default(self):
        """Default REDIS_URL should be redis://localhost:6379/0."""
        from shared.core.infrastructure_config import InfrastructureSettings

        settings = InfrastructureSettings()
        assert settings.REDIS_URL == "redis://localhost:6379/0"

    def test_redis_url_from_env(self, monkeypatch):
        """REDIS_URL should be loaded from environment."""
        monkeypatch.setenv("REDIS_URL", "redis://custom:6380/1")
        
        # Need to reload the module to pick up env var
        import importlib
        from shared.core import infrastructure_config
        importlib.reload(infrastructure_config)
        
        assert infrastructure_config.settings.REDIS_URL == "redis://custom:6380/1"

    def test_has_required_infrastructure_fields(self):
        """InfrastructureSettings should have all required infrastructure fields."""
        from shared.core.infrastructure_config import settings

        # Paths
        assert hasattr(settings, "BASE_DIR")
        assert hasattr(settings, "DATA_DIR")
        
        # Database
        assert hasattr(settings, "DB_PATH")
        
        # Redis
        assert hasattr(settings, "REDIS_URL")

    def test_does_not_have_service_specific_fields(self):
        """InfrastructureSettings should NOT have service-specific fields."""
        from shared.core.infrastructure_config import settings

        # Should NOT have crawler-specific fields
        assert not hasattr(settings, "CRAWL_QUEUE_KEY")
        assert not hasattr(settings, "CRAWL_CONCURRENCY")
        assert not hasattr(settings, "CRAWL_USER_AGENT")
        
        # Should NOT have frontend-specific fields
        assert not hasattr(settings, "ADMIN_USERNAME")
        assert not hasattr(settings, "SECRET_KEY")
        assert not hasattr(settings, "WEB_SERVER_URL")
