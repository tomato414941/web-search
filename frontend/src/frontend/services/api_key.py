"""API Key Service - CRUD and validation for public search API keys."""

import hashlib
import logging
import secrets

from frontend.core.config import settings
from shared.db.search import get_connection, sql_placeholder

logger = logging.getLogger(__name__)

KEY_PREFIX = "pbs_"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (raw_key, key_hash, key_prefix)."""
    token = secrets.token_urlsafe(32)
    raw_key = f"{KEY_PREFIX}{token}"
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


def create_api_key(
    name: str, rate_limit_daily: int | None = None, db_path: str | None = None
) -> dict:
    """Create a new API key. Returns dict with raw_key (shown once to user)."""
    if rate_limit_daily is None:
        rate_limit_daily = settings.API_KEY_DAILY_LIMIT

    raw_key, key_hash, key_prefix = generate_key()
    key_id = secrets.token_hex(16)

    conn = get_connection(db_path or settings.DB_PATH)
    ph = sql_placeholder()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO api_keys (id, key_hash, key_prefix, name, rate_limit_daily)"
            f" VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
            (key_id, key_hash, key_prefix, name, rate_limit_daily),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    return {
        "id": key_id,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "name": name,
        "rate_limit_daily": rate_limit_daily,
    }


def validate_api_key(raw_key: str, db_path: str | None = None) -> dict | None:
    """Validate an API key. Returns key info dict or None if invalid/revoked."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None

    key_hash = _hash_key(raw_key)
    conn = get_connection(db_path or settings.DB_PATH)
    ph = sql_placeholder()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, key_prefix, name, rate_limit_daily, status"
            f" FROM api_keys WHERE key_hash = {ph}",
            (key_hash,),
        )
        row = cur.fetchone()
        cur.close()

        if row is None or row[4] != "active":
            return None

        # Update last_used_at
        cur = conn.cursor()
        cur.execute(
            f"UPDATE api_keys SET last_used_at = NOW() WHERE id = {ph}",
            (row[0],),
        )
        conn.commit()
        cur.close()

        return {
            "id": row[0],
            "key_prefix": row[1],
            "name": row[2],
            "rate_limit_daily": row[3],
        }
    finally:
        conn.close()


def revoke_api_key(key_id: str, db_path: str | None = None) -> bool:
    """Revoke an API key. Returns True if key was found and revoked."""
    conn = get_connection(db_path or settings.DB_PATH)
    ph = sql_placeholder()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE api_keys SET status = 'revoked' WHERE id = {ph} AND status = 'active'",
            (key_id,),
        )
        conn.commit()
        affected = cur.rowcount
        cur.close()
        return affected > 0
    finally:
        conn.close()


def list_api_keys(db_path: str | None = None) -> list[dict]:
    """List all API keys (without hashes)."""
    conn = get_connection(db_path or settings.DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, key_prefix, name, rate_limit_daily, status, created_at, last_used_at"
            " FROM api_keys ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
        cur.close()
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
    finally:
        conn.close()


def get_daily_usage(key_id: str, db_path: str | None = None) -> int:
    """Count today's search requests for a given API key."""
    conn = get_connection(db_path or settings.DB_PATH)
    ph = sql_placeholder()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM search_logs"
            f" WHERE api_key_id = {ph} AND created_at >= CURRENT_DATE",
            (key_id,),
        )
        count = cur.fetchone()[0]
        cur.close()
        return count
    finally:
        conn.close()
