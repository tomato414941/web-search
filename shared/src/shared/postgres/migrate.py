"""Database migration interface (Alembic-based).

Usage:
    from shared.postgres.migrate import migrate
    migrate()  # runs alembic upgrade head

Migrations live in db/alembic/versions/ as Alembic revision files.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ALEMBIC_DIR = Path(__file__).resolve().parents[4] / "db"


def _get_migration_files() -> list[tuple[int, str, Path]]:
    """List Alembic revision files (kept for backward compat)."""
    versions_dir = ALEMBIC_DIR / "alembic" / "versions"
    if not versions_dir.exists():
        return []
    files: list[tuple[int, str, Path]] = []
    for path in sorted(versions_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        parts = path.stem.split("_", 1)
        if len(parts) >= 2 and parts[0].isdigit():
            files.append((int(parts[0]), parts[1], path))
    return files


def migrate() -> int:
    """Run pending Alembic migrations (upgrade head).

    Returns 0 on success.
    """
    from alembic import command
    from alembic.config import Config

    ini_path = str(ALEMBIC_DIR / "alembic.ini")
    if not os.path.exists(ini_path):
        logger.warning("alembic.ini not found at %s, skipping migration", ini_path)
        return 0

    cfg = Config(ini_path)
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations applied (upgrade head)")
    return 0
