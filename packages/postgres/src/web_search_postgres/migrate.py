"""Database migration interface (Alembic-based).

Usage:
    from web_search_postgres.migrate import migrate
    migrate()  # runs alembic upgrade head

Migrations live in db/alembic/versions/ as Alembic revision files.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_alembic_dir() -> Path | None:
    """Resolve the Alembic directory across repo and installed-package layouts."""
    candidates: list[Path] = []

    env_dir = os.getenv("WEB_SEARCH_DB_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    candidates.extend(
        [
            Path.cwd() / "db",
            Path("/app/db"),
            Path(__file__).resolve().parents[4] / "db",
        ]
    )

    for candidate in candidates:
        if (candidate / "alembic.ini").exists():
            return candidate

    return None


def migrate() -> int:
    """Run pending Alembic migrations (upgrade head).

    Returns 0 on success.
    """
    from alembic import command
    from alembic.config import Config

    alembic_dir = _get_alembic_dir()
    if alembic_dir is None:
        logger.warning("alembic.ini not found, skipping migration")
        return 0

    ini_path = str(alembic_dir / "alembic.ini")
    cfg = Config(ini_path)
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations applied (upgrade head)")
    return 0
