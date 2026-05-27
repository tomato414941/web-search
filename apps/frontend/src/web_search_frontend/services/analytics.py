import hashlib
import logging
from typing import Any
from uuid import uuid4

from fastapi import Request, Response
from web_search_telemetry import SearchResultImpression, SearchTelemetryRepository

from web_search_frontend.core.config import settings
from web_search_core.infrastructure_config import Environment
from web_search_frontend.services.db_helpers import db_cursor

logger = logging.getLogger(__name__)

_telemetry_repo = SearchTelemetryRepository

ANON_SESSION_COOKIE = "anon_sid"
ANON_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def get_or_create_anon_session_id(request: Request) -> tuple[str, bool]:
    existing = request.cookies.get(ANON_SESSION_COOKIE)
    if existing:
        return existing, False

    return uuid4().hex, True


def set_anon_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=ANON_SESSION_COOKIE,
        value=session_id,
        max_age=ANON_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.ENVIRONMENT == Environment.PRODUCTION,
        samesite="lax",
    )


def hash_session_id(session_id: str | None) -> str | None:
    if not session_id or not settings.ANALYTICS_SALT:
        return None
    payload = f"{settings.ANALYTICS_SALT}:{session_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snippet_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_impressions(
    hits: list[dict[str, Any]], page: int, per_page: int
) -> list[SearchResultImpression]:
    rank_offset = max(page - 1, 0) * per_page
    impressions: list[SearchResultImpression] = []
    for index, hit in enumerate(hits, start=1):
        impressions.append(
            SearchResultImpression(
                rank=rank_offset + index,
                url=hit["url"],
                title=hit.get("title"),
                score=hit.get("score"),
                snippet_hash=_snippet_hash(hit.get("snip_plain")),
            )
        )
    return impressions


def record_search_telemetry(
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
    hits: list[dict[str, Any]],
) -> str | None:
    try:
        with db_cursor() as (conn, _):
            request_id, impression_ids = _telemetry_repo.record_search(
                conn,
                query=query,
                source=source,
                mode=mode,
                page=page,
                limit=limit,
                result_count=result_count,
                latency_ms=latency_ms,
                session_hash=session_hash,
                user_agent=user_agent,
                impressions=_build_impressions(hits, page, limit),
            )
        for hit, impression_id in zip(hits, impression_ids):
            hit["impression_id"] = impression_id
        return request_id
    except Exception as exc:
        logger.warning(f"Failed to persist search telemetry: {exc}")
        return None


def record_search_result_click(*, impression_id: str, session_hash: str | None) -> bool:
    try:
        with db_cursor() as (conn, _):
            return _telemetry_repo.record_click(
                conn, impression_id=impression_id, session_hash=session_hash
            )
    except Exception as exc:
        logger.warning(f"Failed to persist search click telemetry: {exc}")
        return False
