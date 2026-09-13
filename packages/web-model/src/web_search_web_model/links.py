"""Observed link graph persistence."""

from typing import Any
from urllib.parse import urlparse

from psycopg2.extras import execute_values

from web_search_core.url_admission import URLAdmissionPolicy
from web_search_core.urls import get_domain
from web_search_web_model.archive.outbox import append_observation, transaction
from web_search_web_model.urls import UrlLedgerRepository


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
    def _referring_host(src_url: str) -> str | None:
        try:
            return urlparse(src_url).hostname
        except ValueError:
            return None

    @staticmethod
    def _upsert_url_referring_hosts(
        cur: Any, src_url: str, pairs: list[tuple[str, str]]
    ) -> None:
        referring_host = LinkGraphRepository._referring_host(src_url)
        if not referring_host or not pairs:
            return
        rows = sorted({(dst, referring_host) for _, dst in pairs})
        execute_values(
            cur,
            """
            INSERT INTO url_referring_hosts (dst_url, referring_host)
            VALUES %s
            ON CONFLICT (dst_url, referring_host)
            DO UPDATE SET last_observed_at = NOW()
            """,
            rows,
        )

    def replace_observed_links(self, src_url: str, dst_urls: list[str]) -> int:
        """Replace observed outlinks for a parsed source URL."""
        pairs = self._normalize_pairs(src_url, dst_urls)
        src = self._normalize_url(src_url)
        if not src:
            return 0

        with transaction() as cur:
            append_observation(cur, src, get_domain(src), [dst for _, dst in pairs])
            self._upsert_url_referring_hosts(cur, src, pairs)
            # Frontier refill uses the ledger, including cross-host discoveries.
            UrlLedgerRepository(self.url_admission_policy).record_in_transaction(
                cur, [src, *(dst for _, dst in pairs)]
            )
        return len(pairs)
