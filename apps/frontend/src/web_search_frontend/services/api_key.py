"""API Key Service - CRUD and validation for public search API keys."""

import hashlib
import logging
import secrets

from web_search_frontend.core.config import settings
from web_search_frontend.services.db_helpers import db_cursor
from web_search_postgres.repositories.api_key_repo import ApiKeyRepository

logger = logging.getLogger(__name__)

KEY_PREFIX = "pbs_"

_repo = ApiKeyRepository


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (raw_key, key_hash, key_prefix)."""
    token = secrets.token_urlsafe(32)
    raw_key = f"{KEY_PREFIX}{token}"
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


def create_api_key(name: str, rate_limit_daily: int | None = None) -> dict:
    """Create a new API key. Returns dict with raw_key (shown once to user)."""
    if rate_limit_daily is None:
        rate_limit_daily = settings.API_KEY_DAILY_LIMIT

    raw_key, key_hash, key_prefix = generate_key()
    key_id = secrets.token_hex(16)

    with db_cursor() as (conn, _):
        _repo.create(conn, key_id, key_hash, key_prefix, name, rate_limit_daily)

    return {
        "id": key_id,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "name": name,
        "rate_limit_daily": rate_limit_daily,
    }


def validate_api_key(raw_key: str) -> dict | None:
    """Validate an API key. Returns key info dict or None if invalid/revoked."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None

    key_hash = _hash_key(raw_key)
    with db_cursor() as (conn, _):
        row = _repo.find_by_hash(conn, key_hash)
        if row is None or row[4] != "active":
            return None

        _repo.update_last_used(conn, row[0])

        return {
            "id": row[0],
            "key_prefix": row[1],
            "name": row[2],
            "rate_limit_daily": row[3],
        }


def revoke_api_key(key_id: str) -> bool:
    """Revoke an API key. Returns True if key was found and revoked."""
    with db_cursor() as (conn, _):
        return _repo.revoke(conn, key_id) > 0


def list_api_keys() -> list[dict]:
    """List all API keys (without hashes)."""
    with db_cursor() as (conn, _):
        rows = _repo.list_all(conn)
        return [
            {
                "id": r[0],
                "key_prefix": r[1],
                "name": r[2],
                "rate_limit_daily": r[3],
                "status": r[4],
                "created_at": str(r[5]) if r[5] else None,
                "last_used_at": str(r[6]) if r[6] else None,
            }
            for r in rows
        ]


def get_daily_usage(key_id: str) -> int:
    """Count today's search requests for a given API key."""
    with db_cursor() as (conn, _):
        return _repo.get_daily_usage(conn, key_id)
