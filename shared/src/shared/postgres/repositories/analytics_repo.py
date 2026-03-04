"""Repository for search_logs and search_events tables."""

from typing import Any


class AnalyticsRepository:
    """Data-access layer for search analytics (search_logs + search_events)."""

    # -- search_logs ----------------------------------------------------------

    @staticmethod
    def insert_search_log(
        conn: Any,
        query: str,
        result_count: int,
        search_mode: str,
        user_agent: str | None,
        api_key_id: str | None,
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO search_logs"
            " (query, result_count, search_mode, user_agent, api_key_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (query, result_count, search_mode, user_agent, api_key_id),
        )
        conn.commit()
        cur.close()

    @staticmethod
    def count_since(
        conn: Any,
        cutoff: str,
        exclusion_sql: str = "",
        exclusion_params: tuple = (),
    ) -> int:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM search_logs WHERE created_at >= %s{exclusion_sql}",
            (cutoff, *exclusion_params),
        )
        count = cur.fetchone()[0]
        cur.close()
        return count

    @staticmethod
    def top_queries(
        conn: Any,
        cutoff: str,
        limit: int = 20,
        exclusion_sql: str = "",
        exclusion_params: tuple = (),
    ) -> list[dict[str, Any]]:
        cur = conn.cursor()
        cur.execute(
            f"SELECT query, COUNT(*) as count, AVG(result_count) as avg_results"
            f" FROM search_logs"
            f" WHERE created_at >= %s{exclusion_sql}"
            f" GROUP BY query ORDER BY count DESC LIMIT %s",
            (cutoff, *exclusion_params, limit),
        )
        rows = [
            {"query": row[0], "count": row[1], "avg_results": round(row[2], 1)}
            for row in cur.fetchall()
        ]
        cur.close()
        return rows

    @staticmethod
    def zero_hit_queries(
        conn: Any,
        cutoff: str,
        limit: int = 20,
        exclusion_sql: str = "",
        exclusion_params: tuple = (),
    ) -> list[dict[str, Any]]:
        cur = conn.cursor()
        cur.execute(
            f"SELECT query, COUNT(*) as count"
            f" FROM search_logs"
            f" WHERE result_count = 0 AND created_at >= %s{exclusion_sql}"
            f" GROUP BY query ORDER BY count DESC LIMIT %s",
            (cutoff, *exclusion_params, limit),
        )
        rows = [{"query": row[0], "count": row[1]} for row in cur.fetchall()]
        cur.close()
        return rows

    @staticmethod
    def today_summary(
        conn: Any,
        cutoff: str,
        exclusion_sql: str = "",
        exclusion_params: tuple = (),
    ) -> dict[str, int]:
        """Return today's total, unique queries, and zero-hit count."""
        cur = conn.cursor()
        cur.execute(
            f"SELECT"
            f"  COUNT(*) as total,"
            f"  COUNT(DISTINCT query) as unique_queries,"
            f"  SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) as zero_hits"
            f" FROM search_logs"
            f" WHERE created_at >= %s{exclusion_sql}",
            (cutoff, *exclusion_params),
        )
        row = cur.fetchone()
        cur.close()
        return {
            "total": row[0] or 0,
            "unique_queries": row[1] or 0,
            "zero_hits": row[2] or 0,
        }

    # -- search_events --------------------------------------------------------

    @staticmethod
    def insert_search_event(
        conn: Any,
        *,
        event_type: str,
        query: str,
        query_norm: str,
        request_id: str | None,
        session_hash: str | None,
        result_count: int | None,
        clicked_url: str | None,
        clicked_rank: int | None,
        latency_ms: int | None,
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO search_events"
            " (event_type, query, query_norm, request_id, session_hash,"
            "  result_count, clicked_url, clicked_rank, latency_ms)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                event_type,
                query,
                query_norm,
                request_id,
                session_hash,
                result_count,
                clicked_url,
                clicked_rank,
                latency_ms,
            ),
        )
        conn.commit()
        cur.close()

    @staticmethod
    def get_impressions(
        conn: Any, cutoff: str
    ) -> list[tuple[str | None, int | None, int | None]]:
        """Return (request_id, result_count, latency_ms) for impressions."""
        cur = conn.cursor()
        cur.execute(
            "SELECT request_id, result_count, latency_ms"
            " FROM search_events"
            " WHERE event_type = %s AND created_at >= %s",
            ("impression", cutoff),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def get_clicked_request_ids(conn: Any, cutoff: str) -> set[str]:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT request_id"
            " FROM search_events"
            " WHERE event_type = %s AND created_at >= %s"
            " AND request_id IS NOT NULL",
            ("click", cutoff),
        )
        ids = {row[0] for row in cur.fetchall() if row[0]}
        cur.close()
        return ids

    @staticmethod
    def get_click_ranks(conn: Any, cutoff: str) -> list[int]:
        cur = conn.cursor()
        cur.execute(
            "SELECT clicked_rank"
            " FROM search_events"
            " WHERE event_type = %s AND created_at >= %s"
            " AND clicked_rank IS NOT NULL",
            ("click", cutoff),
        )
        ranks = [int(row[0]) for row in cur.fetchall() if row[0] is not None]
        cur.close()
        return ranks

    # -- documents (read-only aggregates for analytics) -----------------------

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
        cur.execute("SELECT COUNT(*) FROM crawl_queue")
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
