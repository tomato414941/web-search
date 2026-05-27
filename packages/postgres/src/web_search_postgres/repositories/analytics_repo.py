"""Repository for non-search-telemetry analytics read models."""

from typing import Any


class AnalyticsRepository:
    """Data-access layer for document, frontier, and crawl analytics."""

    # -- documents (read-only aggregates for analytics) -----------------------

    @staticmethod
    def document_summary(conn: Any, cutoff: str) -> dict[str, Any]:
        cur = conn.cursor()
        cur.execute(
            "SELECT"
            "  COALESCE("
            "    (SELECT reltuples::bigint FROM pg_class"
            "     WHERE oid = to_regclass('documents')),"
            "    0"
            "  ) AS total_estimate,"
            "  COUNT(*) FILTER ("
            "    WHERE indexed_at IS NOT NULL AND indexed_at >= %s"
            "  ) AS indexed_since,"
            "  MAX(indexed_at) AS last_indexed_at"
            " FROM documents",
            (cutoff,),
        )
        row = cur.fetchone()
        cur.close()
        total_estimate = int(row[0] or 0)
        indexed_since = int(row[1] or 0)
        return {
            "total_documents": max(total_estimate, indexed_since),
            "indexed_since": indexed_since,
            "max_indexed_at": row[2],
        }

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

    @staticmethod
    def count_indexed_since(conn: Any, cutoff: str) -> int:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM documents"
            " WHERE indexed_at IS NOT NULL AND indexed_at >= %s",
            (cutoff,),
        )
        count = int(cur.fetchone()[0] or 0)
        cur.close()
        return count

    @staticmethod
    def count_total_documents(conn: Any) -> int:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        count = cur.fetchone()[0]
        cur.close()
        return count

    @staticmethod
    def max_indexed_at(conn: Any) -> Any:
        cur = conn.cursor()
        cur.execute(
            "SELECT MAX(indexed_at) FROM documents WHERE indexed_at IS NOT NULL"
        )
        result = cur.fetchone()
        cur.close()
        return result[0] if result else None

    @staticmethod
    def count_short_content_since(conn: Any, cutoff: str, min_words: int = 80) -> int:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM documents"
            " WHERE indexed_at IS NOT NULL AND word_count < %s AND indexed_at >= %s",
            (min_words, cutoff),
        )
        count = int(cur.fetchone()[0] or 0)
        cur.close()
        return count

    @staticmethod
    def content_duplicate_counts(conn: Any, cutoff: str) -> tuple[int, int]:
        """Return (total_with_content, unique_contents) for dedup analysis."""
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT md5(content))"
            " FROM documents"
            " WHERE indexed_at IS NOT NULL"
            "   AND content IS NOT NULL"
            "   AND content <> ''"
            "   AND indexed_at >= %s",
            (cutoff,),
        )
        row = cur.fetchone()
        cur.close()
        return (int(row[0] or 0), int(row[1] or 0))

    # -- urls (read-only for analytics) ---------------------------------------

    @staticmethod
    def count_pending_urls(conn: Any) -> int:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM frontier_entries WHERE status = 'pending'")
        count = int(cur.fetchone()[0] or 0)
        cur.close()
        return count

    # -- crawl_logs (read-only for analytics) ---------------------------------

    @staticmethod
    def crawl_status_counts(
        conn: Any,
        cutoff_epoch: int,
        statuses: tuple,
    ) -> dict[str, int]:
        placeholders = ", ".join(["%s"] * len(statuses))
        cur = conn.cursor()
        cur.execute(
            f"SELECT status, COUNT(*)"
            f" FROM crawl_logs"
            f" WHERE created_at >= %s AND status IN ({placeholders})"
            f" GROUP BY status",
            (cutoff_epoch, *statuses),
        )
        counts = {str(status): int(count) for status, count in cur.fetchall()}
        cur.close()
        return counts

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def table_exists(conn: Any, table_name: str) -> bool:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_schema = 'public' AND table_name = %s"
                ")",
                (table_name,),
            )
            return bool(cur.fetchone()[0])
        finally:
            cur.close()
