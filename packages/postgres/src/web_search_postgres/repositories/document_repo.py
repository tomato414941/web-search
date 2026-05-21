"""Repository for documents, links, and related search metadata."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from web_search_postgres.search import get_connection, sql_placeholder


class DocumentRepository:
    """Data-access helpers for indexed documents and related metadata."""

    @staticmethod
    def fetch_by_url(conn: Any, url: str) -> tuple | None:
        cur = conn.cursor()
        cur.execute(
            "SELECT title, content, word_count, indexed_at, published_at"
            " FROM documents WHERE url = %s",
            (url,),
        )
        row = cur.fetchone()
        cur.close()
        return row

    @staticmethod
    def upsert_document(
        conn: Any,
        *,
        url: str,
        title: str,
        content: str,
        word_count: int,
        indexed_at: str,
        published_at: str | None,
    ) -> None:
        ph = sql_placeholder()
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO documents (url, title, content, word_count, indexed_at, published_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                word_count = EXCLUDED.word_count,
                indexed_at = EXCLUDED.indexed_at,
                published_at = COALESCE(EXCLUDED.published_at, documents.published_at)
            """,
            (url, title, content, word_count, indexed_at, published_at),
        )
        cur.close()

    @staticmethod
    def delete_by_url(conn: Any, url: str) -> None:
        ph = sql_placeholder()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM documents WHERE url = {ph}", (url,))
        cur.close()

    @staticmethod
    def replace_links(conn: Any, src_url: str, outlinks: list[str]) -> None:
        ph = sql_placeholder()
        cur = conn.cursor()
        savepoint = "sp_save_links"
        try:
            cur.execute(f"SAVEPOINT {savepoint}")
            cur.execute(f"DELETE FROM links WHERE src = {ph}", (src_url,))
            pairs = [(src_url, dst) for dst in outlinks if dst != src_url]
            if pairs:
                cur.executemany(
                    f"INSERT INTO links (src, dst) VALUES ({ph}, {ph}) "
                    "ON CONFLICT DO NOTHING",
                    pairs,
                )
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        finally:
            cur.close()

    @staticmethod
    def fetch_link_ranks(url: str) -> tuple[float, float]:
        ph = sql_placeholder()
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT score FROM page_ranks WHERE url = {ph}", (url,))
            row = cur.fetchone()
            page_rank = float(row[0]) if row else 0.0

            domain = urlparse(url).netloc
            cur.execute(
                f"SELECT score FROM domain_ranks WHERE domain = {ph}", (domain,)
            )
            row = cur.fetchone()
            domain_rank = float(row[0]) if row else 0.0
            cur.close()
            return page_rank, domain_rank
        finally:
            conn.close()

    @staticmethod
    def fetch_link_rank_map(urls: Sequence[str]) -> dict[str, tuple[float, float]]:
        if not urls:
            return {}
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT url, score FROM page_ranks WHERE url = ANY(%s)",
                (list(urls),),
            )
            page_ranks = {str(url): float(score) for url, score in cur.fetchall()}

            domains = list({urlparse(url).netloc for url in urls})
            cur.execute(
                "SELECT domain, score FROM domain_ranks WHERE domain = ANY(%s)",
                (domains,),
            )
            domain_ranks = {
                str(domain): float(score) for domain, score in cur.fetchall()
            }
            cur.close()
            return {
                url: (
                    page_ranks.get(url, 0.0),
                    domain_ranks.get(urlparse(url).netloc, 0.0),
                )
                for url in urls
            }
        finally:
            conn.close()

    @staticmethod
    def fetch_origin_score(url: str) -> tuple[float, str]:
        ph = sql_placeholder()
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT score, origin_type FROM information_origins WHERE url = {ph}",
                (url,),
            )
            row = cur.fetchone()
            cur.close()
            if row:
                return float(row[0]), str(row[1])
            return 0.5, "river"
        finally:
            conn.close()

    @staticmethod
    def count_documents() -> int:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM documents")
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    @staticmethod
    def count_documents_with_published_at() -> int:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM documents WHERE published_at IS NOT NULL")
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    @staticmethod
    def fetch_documents_for_temporal_anchor(
        *, limit: int, offset: int
    ) -> list[tuple[str, datetime | None]]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT url, published_at FROM documents ORDER BY url LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = [(str(url), published_at) for url, published_at in cur.fetchall()]
            cur.close()
            return rows
        finally:
            conn.close()

    @staticmethod
    def fetch_documents_for_factual_density(
        *, limit: int, offset: int
    ) -> list[tuple[str, str, int]]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT url, content, word_count "
                "FROM documents ORDER BY url LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = [
                (str(url), str(content or ""), int(word_count or 0))
                for url, content, word_count in cur.fetchall()
            ]
            cur.close()
            return rows
        finally:
            conn.close()

    @staticmethod
    def fetch_documents_for_opensearch(
        *, limit: int, offset: int
    ) -> list[tuple[str, str, str, int, datetime | None]]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT url, title, content, word_count, indexed_at "
                "FROM documents ORDER BY url LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = [
                (
                    str(url),
                    str(title or ""),
                    str(content or ""),
                    int(word_count or 0),
                    indexed_at,
                )
                for url, title, content, word_count, indexed_at in cur.fetchall()
            ]
            cur.close()
            return rows
        finally:
            conn.close()

    @staticmethod
    def sample_document_urls(limit: int) -> list[str]:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT url FROM documents ORDER BY random() LIMIT %s", (limit,)
            )
            rows = [str(url) for (url,) in cur.fetchall()]
            cur.close()
            return rows
        finally:
            conn.close()

    @staticmethod
    def count_documents_estimate() -> int:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = 'documents'"
            )
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row and row[0] >= 0 else 0
        finally:
            conn.close()
