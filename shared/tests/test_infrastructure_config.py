"""Test infrastructure configuration."""


class TestInfrastructureSettings:
    """Test InfrastructureSettings class."""

    def test_has_required_infrastructure_fields(self):
        """InfrastructureSettings should have all required infrastructure fields."""
        from shared.core.infrastructure_config import settings

        # Paths
        assert hasattr(settings, "BASE_DIR")
        assert hasattr(settings, "DATA_DIR")

        # Database
        assert hasattr(settings, "DB_PATH")

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

        # Should NOT have Redis fields (removed)
        assert not hasattr(settings, "REDIS_URL")
