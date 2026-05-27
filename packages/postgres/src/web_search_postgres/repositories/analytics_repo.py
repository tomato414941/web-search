"""Repository for admin analytics read models."""

from typing import Any


class AnalyticsRepository:
    """Data-access layer for document analytics."""

    @staticmethod
    def document_count_estimate(conn: Any) -> int:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE("
            "  (SELECT reltuples::bigint FROM pg_class"
            "   WHERE oid = to_regclass('documents')),"
            "  0"
            ")"
        )
        estimate = int(cur.fetchone()[0] or 0)
        cur.close()
        return estimate
