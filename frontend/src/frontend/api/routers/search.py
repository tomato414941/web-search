"""Search UI Router - HTML search page."""

import asyncio
import time
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Cookie, BackgroundTasks
from fastapi.responses import HTMLResponse

from frontend.core.config import settings
from frontend.i18n.messages import MESSAGES
from frontend.services.search import search_service
from frontend.services.analytics import (
    log_search,
    log_impression_event,
    get_or_set_anon_session_id,
    hash_session_id,
)
from frontend.api.templates import templates
from frontend.api.middleware.rate_limiter import limiter
from shared.contracts.enums import SearchMode

router = APIRouter()


def _parse_pos_int(value: str | None, default: int, *, min_v: int = 1) -> int:
    try:
        x = int(value) if value is not None else default
    except ValueError:
        x = default
    return max(x, min_v)


def _build_search_url(
    *,
    query: str | None,
    page: int | None = None,
    mode: str | None = None,
    lang: str | None = None,
) -> str:
    params: list[tuple[str, str]] = []
    if query:
        params.append(("q", query))
    if page is not None:
        params.append(("page", str(page)))
    if mode:
        params.append(("mode", mode))
    if lang:
        params.append(("lang", lang))
    encoded = urlencode(params)
    return f"/?{encoded}" if encoded else "/"


def _detect_language(
    lang_param: str | None, lang_cookie: str | None, accept_language: str | None
) -> str:
    """Detect language priority: Query > Cookie > Header > Default(en)"""
    if lang_param in MESSAGES:
        return lang_param
    if lang_cookie in MESSAGES:
        return lang_cookie
    if accept_language:
        if "ja" in accept_language.lower().split(",")[0]:
            return "ja"
    return "en"


@router.get("/", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def search_page(
    request: Request,
    background_tasks: BackgroundTasks,
    q: str | None = None,
    page: str | None = None,
    mode: str | None = None,
    ui_mode: str | None = Cookie(default="modern"),
    lang: str | None = None,
    user_lang: str | None = Cookie(default=None, alias="lang"),
):
    """Search Page"""
    started_at = time.perf_counter()
    current_lang = _detect_language(
        lang, user_lang, request.headers.get("accept-language")
    )
    msg = MESSAGES[current_lang]

    current_mode = mode if mode in ["simple", "modern"] else ui_mode
    if current_mode not in ["simple", "modern"]:
        current_mode = "modern"

    query = (q or "").strip() or None
    if query is not None and len(query) > settings.MAX_QUERY_LEN:
        query = query[: settings.MAX_QUERY_LEN]

    page_number = min(_parse_pos_int(page, 1), settings.MAX_PAGE)
    per_page = min(settings.RESULTS_LIMIT, settings.MAX_PER_PAGE)
    request_id = uuid.uuid4().hex if query else None

    effective_search_mode = SearchMode.BM25
    current_page = page_number

    result = (
        await asyncio.to_thread(
            search_service.search, query, per_page, page_number, effective_search_mode
        )
        if query
        else None
    )
    if result is not None:
        current_page = result["page"]

    resp = templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "q": query,
            "result": result,
            "mode": current_mode,
            "lang": current_lang,
            "msg": msg,
            "request_id": request_id,
            "mode_urls": {
                "modern": _build_search_url(
                    query=query,
                    page=current_page if query else None,
                    mode="modern",
                    lang=current_lang,
                ),
                "simple": _build_search_url(
                    query=query,
                    page=current_page if query else None,
                    mode="simple",
                    lang=current_lang,
                ),
            },
            "lang_urls": {
                "en": _build_search_url(
                    query=query,
                    page=current_page if query else None,
                    mode=current_mode,
                    lang="en",
                ),
                "ja": _build_search_url(
                    query=query,
                    page=current_page if query else None,
                    mode=current_mode,
                    lang="ja",
                ),
            },
            "prev_page_url": (
                _build_search_url(
                    query=query,
                    page=result["page"] - 1,
                    mode=current_mode,
                    lang=current_lang,
                )
                if result is not None and result["page"] > 1
                else None
            ),
            "next_page_url": (
                _build_search_url(
                    query=query,
                    page=result["page"] + 1,
                    mode=current_mode,
                    lang=current_lang,
                )
                if result is not None and result["page"] < result["last_page"]
                else None
            ),
        },
    )

    if query and result is not None and request_id is not None:
        user_agent = request.headers.get("user-agent")
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        session_id = get_or_set_anon_session_id(request, resp)
        session_hash = hash_session_id(session_id)
        background_tasks.add_task(
            log_search, query, result["total"], user_agent, effective_search_mode
        )
        background_tasks.add_task(
            log_impression_event,
            query=query,
            request_id=request_id,
            result_count=result["total"],
            session_hash=session_hash,
            latency_ms=latency_ms,
        )

    if mode in ["simple", "modern"]:
        resp.set_cookie(key="ui_mode", value=mode)

    if lang in MESSAGES:
        resp.set_cookie(key="lang", value=lang)

    return resp
