from fastapi import APIRouter, Request, Response, Cookie
from fastapi.responses import JSONResponse, HTMLResponse

from frontend.core.config import settings
from frontend.i18n.messages import MESSAGES
from frontend.services.search import search_service
from frontend.api.templates import templates
from frontend.api.middleware.rate_limiter import limiter

router = APIRouter()


def _parse_pos_int(value: str | None, default: int, *, min_v: int = 1) -> int:
    try:
        x = int(value) if value is not None else default
    except ValueError:
        x = default
    return max(x, min_v)


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
    response: Response,
    q: str | None = None,
    page: str | None = None,
    mode: str | None = None,
    ui_mode: str | None = Cookie(default="modern"),
    lang: str | None = None,
    user_lang: str | None = Cookie(default=None, alias="lang"),
):
    """Search Page"""
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

    # Use Service
    result = search_service.search(query, per_page, page_number) if query else None

    resp = templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "q": query,
            "result": result,
            "mode": current_mode,
            "lang": current_lang,
            "msg": msg,
        },
    )

    if mode in ["simple", "modern"]:
        resp.set_cookie(key="ui_mode", value=mode)

    if lang in MESSAGES:
        resp.set_cookie(key="lang", value=lang)

    return resp


@router.get("/api/search")
@limiter.limit("100/minute")
async def api_search(
    request: Request,
    q: str | None = None,
    limit: str | None = None,
    page: str | None = None,
):
    """Search API (JSON)"""
    query = (q or "").strip()
    if len(query) > settings.MAX_QUERY_LEN:
        query = query[: settings.MAX_QUERY_LEN]

    per_page = min(_parse_pos_int(limit, settings.RESULTS_LIMIT), settings.MAX_PER_PAGE)
    page_number = min(_parse_pos_int(page, 1), settings.MAX_PAGE)

    data = (
        search_service.search(query, per_page, page_number)
        if query
        else search_service._empty_result(per_page)
    )
    return JSONResponse(data)


@router.get("/api/predict")
@limiter.limit("30/minute")
async def api_predict(
    request: Request, url: str, parent_score: float = 100.0, visits: int = 0
):
    """
    Predict Crawler Score for a URL.

    Proxies the request to the Crawler Service's scoring endpoint.

    Args:
        url: The URL to evaluate
        parent_score: Score of the parent page (default 100.0)
        visits: Number of times this domain has been visited (default 0)
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.CRAWLER_SERVICE_URL}/score/predict",
                json={
                    "url": url,
                    "parent_score": parent_score,
                    "visits": visits,
                },
            )
            if resp.status_code == 200:
                return JSONResponse(resp.json())
            else:
                return JSONResponse(
                    {"error": "Crawler service error", "detail": resp.text},
                    status_code=502,
                )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": "Crawler service unavailable", "detail": str(e)},
            status_code=503,
        )
