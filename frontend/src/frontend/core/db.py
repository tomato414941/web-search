"""
SQLite Database Module (Frontend)

Re-exports shared database module for backward compatibility.
Frontend uses read operations only (CQRS pattern).
"""

# Re-export from shared kernel for backward compatibility
from shared.db.search import (
    SCHEMA_SQL,
    open_db,
    ensure_db,
)

__all__ = ["SCHEMA_SQL", "open_db", "ensure_db"]
