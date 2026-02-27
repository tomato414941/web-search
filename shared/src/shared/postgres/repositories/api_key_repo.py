"""Repository for api_keys table."""

from typing import Any


class ApiKeyRepository:
    """Data-access layer for api_keys and related usage queries."""

    @staticmethod
    def create(
        conn: Any,
        key_id: str,
        key_hash: str,
        key_prefix: str,
        name: str,
        rate_limit_daily: int,
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO api_keys (id, key_hash, key_prefix, name, rate_limit_daily)"
            " VALUES (%s, %s, %s, %s, %s)",
            (key_id, key_hash, key_prefix, name, rate_limit_daily),
        )
        conn.commit()
        cur.close()

    @staticmethod
    def find_by_hash(conn: Any, key_hash: str) -> tuple | None:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, key_prefix, name, rate_limit_daily, status"
            " FROM api_keys WHERE key_hash = %s",
            (key_hash,),
        )
        row = cur.fetchone()
        cur.close()
        return row

    @staticmethod
    def update_last_used(conn: Any, key_id: str) -> None:
        cur = conn.cursor()
        cur.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s",
            (key_id,),
        )
        conn.commit()
        cur.close()

    @staticmethod
    def revoke(conn: Any, key_id: str) -> int:
        cur = conn.cursor()
        cur.execute(
            "UPDATE api_keys SET status = 'revoked'"
            " WHERE id = %s AND status = 'active'",
            (key_id,),
        )
        affected = cur.rowcount
        conn.commit()
        cur.close()
        return affected

    @staticmethod
    def list_all(conn: Any) -> list[tuple]:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, key_prefix, name, rate_limit_daily, status,"
            " created_at, last_used_at"
            " FROM api_keys ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def get_daily_usage(conn: Any, key_id: str) -> int:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM search_logs"
            " WHERE api_key_id = %s AND created_at >= CURRENT_DATE",
            (key_id,),
        )
        count = cur.fetchone()[0]
        cur.close()
        return count
