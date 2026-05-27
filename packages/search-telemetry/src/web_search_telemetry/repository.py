from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class SearchResultImpression:
    rank: int
    url: str
    title: str | None
    score: float | None
    snippet_hash: str | None


def normalize_query(query: str) -> str:
    return " ".join((query or "").strip().lower().split())


class SearchTelemetryRepository:
    """Persistence boundary for search experience telemetry."""

    @staticmethod
    def record_search(
        conn: Any,
        *,
        query: str,
        source: str,
        mode: str,
        page: int,
        limit: int,
        result_count: int,
        latency_ms: int | None,
        session_hash: str | None,
        user_agent: str | None,
        impressions: list[SearchResultImpression],
    ) -> tuple[str, list[str]]:
        search_request_id = uuid4().hex
        impression_ids = [uuid4().hex for _ in impressions]

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO search_requests"
            " (id, query, query_norm, source, mode, page, result_limit,"
            "  result_count, latency_ms, session_hash, user_agent)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                search_request_id,
                query,
                normalize_query(query),
                source,
                mode,
                page,
                limit,
                result_count,
                latency_ms,
                session_hash,
                user_agent,
            ),
        )

        if impressions:
            cur.executemany(
                "INSERT INTO search_result_impressions"
                " (id, search_request_id, rank, url, title, score, snippet_hash)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        impression_id,
                        search_request_id,
                        impression.rank,
                        impression.url,
                        impression.title,
                        impression.score,
                        impression.snippet_hash,
                    )
                    for impression_id, impression in zip(impression_ids, impressions)
                ],
            )

        conn.commit()
        cur.close()
        return search_request_id, impression_ids

    @staticmethod
    def record_click(
        conn: Any, *, impression_id: str, session_hash: str | None
    ) -> bool:
        cur = conn.cursor()
        cur.execute(
            "SELECT search_request_id FROM search_result_impressions WHERE id = %s",
            (impression_id,),
        )
        row = cur.fetchone()
        if row is None:
            cur.close()
            return False

        cur.execute(
            "INSERT INTO search_result_clicks"
            " (id, search_request_id, impression_id, session_hash)"
            " VALUES (%s, %s, %s, %s)",
            (uuid4().hex, row[0], impression_id, session_hash),
        )
        conn.commit()
        cur.close()
        return True

    @staticmethod
    def request_metrics(
        conn: Any, cutoff: str
    ) -> list[tuple[str, int | None, int | None]]:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, result_count, latency_ms"
            " FROM search_requests"
            " WHERE created_at >= %s",
            (cutoff,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    @staticmethod
    def clicked_request_ids(conn: Any, cutoff: str) -> set[str]:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT c.search_request_id"
            " FROM search_result_clicks c"
            " WHERE c.clicked_at >= %s",
            (cutoff,),
        )
        ids = {row[0] for row in cur.fetchall() if row[0]}
        cur.close()
        return ids

    @staticmethod
    def click_ranks(conn: Any, cutoff: str) -> list[int]:
        cur = conn.cursor()
        cur.execute(
            "SELECT i.rank"
            " FROM search_result_clicks c"
            " JOIN search_result_impressions i ON i.id = c.impression_id"
            " WHERE c.clicked_at >= %s",
            (cutoff,),
        )
        ranks = [int(row[0]) for row in cur.fetchall() if row[0] is not None]
        cur.close()
        return ranks
