"""
DEPRECATED: This config is maintained for backward compatibility only.

For new code, use:
- shared.core.infrastructure_config for infrastructure settings
- app.core.config (in crawler) for crawler-specific settings  
- frontend.core.config for frontend-specific settings
"""
from shared.core.infrastructure_config import settings

# Re-export for backward compatibility
__all__ = ["settings"]
