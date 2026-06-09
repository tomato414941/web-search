"""Observed link graph persistence."""

from typing import Any

from psycopg2.extras import execute_values

from web_search_core.url_admission import URLAdmissionPolicy
from web_search_postgres.search import get_connection


class LinkGraphRepository:
    """Persistent graph of URL-to-URL links observed while parsing pages."""

    def __init__(self, url_admission_policy: URLAdmissionPolicy):
        self.url_admission_policy = url_admission_policy

    def _normalize_url(self, url: str) -> str | None:
        decision = self.url_admission_policy.evaluate(url)
        return decision.normalized_url

    def _normalize_pairs(
        self, src_url: str, dst_urls: list[str]
    ) -> list[tuple[str, str]]:
        src = self._normalize_url(src_url)
        if not src:
            return []
        pairs: dict[tuple[str, str], None] = {}
        for dst_url in dst_urls:
            if not dst_url:
                continue
            dst = self._normalize_url(dst_url)
            if not dst or dst == src:
                continue
            pairs.setdefault((src, dst), None)
        return sorted(pairs)

    @staticmethod
    def _replace_links(cur: Any, src_url: str, pairs: list[tuple[str, str]]) -> None:
        cur.execute("DELETE FROM links WHERE src = %s", (src_url,))
        if pairs:
            execute_values(
                cur,
                """
                INSERT INTO links (src, dst)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                pairs,
            )

    def replace_observed_links(self, src_url: str, dst_urls: list[str]) -> int:
        """Replace observed outlinks for a parsed source URL."""
        pairs = self._normalize_pairs(src_url, dst_urls)
        src = self._normalize_url(src_url)
        if not src:
            return 0

        con = get_connection()
        try:
            cur = con.cursor()
            try:
                self._replace_links(cur, src, pairs)
                con.commit()
            finally:
                cur.close()
            return len(pairs)
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()
