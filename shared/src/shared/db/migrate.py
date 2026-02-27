"""Backward-compatible re-exports. Use shared.postgres.migrate instead."""

from shared.postgres.migrate import (  # noqa: F401
    _get_migration_files,
    migrate,
)
