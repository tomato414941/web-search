"""Admin Dashboard Router with Authentication."""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from frontend.api.deps_admin import (
    check_csrf_or_redirect,
    require_admin_session,
    require_admin_session_api,
)
from frontend.api.middleware.rate_limiter import limiter
from frontend.api.routers.admin_crawlers import router as crawlers_router
from frontend.api.routers.admin_indexer import router as indexer_router
from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services.admin_analytics import get_analytics_data
from frontend.services.admin_auth import (
    CSRF_FORM_FIELD,
    SESSION_COOKIE_NAME,
    add_csrf_cookie,
    add_session_cookie,
    create_session,
    generate_csrf_token,
    get_csrf_token,
    validate_csrf_token,
)
from frontend.services.admin_dashboard import get_dashboard_data
from frontend.services.api_key import (
    create_api_key,
    list_api_keys,
    revoke_api_key,
)
from frontend.services.crawler_admin_client import (
    fetch_frontier_stats,
    fetch_history,
    fetch_seeds_page,
    import_tranco as import_tranco_seeds,
    add_seed as crawler_add_seed,
    delete_seed as crawler_delete_seed,
    enqueue_url,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _parse_tranco_count(raw_count: str | None) -> int:
    normalized = (raw_count or "").strip().replace(",", "")
    if not normalized.isdigit():
        raise ValueError("Count must be an integer between 1 and 10000")

    count = int(normalized)
    if count < 1 or count > 10000:
        raise ValueError("Count must be between 1 and 10000")
    return count


@router.get("/login")
async def login_page(request: Request, error: str = ""):
    csrf_token = get_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "admin/login.html",
        {"request": request, "error": error, "csrf_token": csrf_token},
    )
    return add_csrf_cookie(response, csrf_token)


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/login?error=Invalid+request", status_code=303
        )

    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        token = create_session()
        new_csrf = generate_csrf_token()
        response = RedirectResponse(url="/admin/", status_code=303)
        add_session_cookie(response, token)
        add_csrf_cookie(response, new_csrf)
        return response

    return RedirectResponse(
        url="/admin/login?error=Invalid+credentials", status_code=303
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/")
async def dashboard(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
    data = await get_dashboard_data()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "request": request,
            "data": data,
            "crawler_url": settings.CRAWLER_SERVICE_URL,
            "csrf_token": csrf_token,
        },
    )


@router.get("/seeds")
async def seeds_page(
    request: Request,
    page: int = 1,
    success: str = "",
    error: str = "",
    _auth: None = Depends(require_admin_session),
):
    seed_page = await fetch_seeds_page(page=page)
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/seeds.html",
        {
            "request": request,
            "seeds": seed_page["items"],
            "seed_page": seed_page,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
        },
    )


@router.get("/queue")
async def queue_page(
    request: Request,
    success: str = "",
    error: str = "",
    _auth: None = Depends(require_admin_session),
):
    frontier = await fetch_frontier_stats()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/queue.html",
        {
            "request": request,
            "frontier": frontier,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
        },
    )


@router.get("/history")
async def history_page(
    request: Request,
    url: str = "",
    _auth: None = Depends(require_admin_session),
):
    history_logs = await fetch_history(url_filter=url)
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/history.html",
        {
            "request": request,
            "history_logs": history_logs,
            "url_filter": url,
            "csrf_token": csrf_token,
        },
    )


@router.post("/seeds")
async def add_seed(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/seeds?error=Invalid+request")
    try:
        await crawler_add_seed(url)
        return RedirectResponse(
            url=f"/admin/seeds?success={quote(f'Added seed {url}', safe='')}",
            status_code=303,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(exc), safe='')}",
            status_code=303,
        )
    except Exception:
        logger.exception("Failed to add seed %s", url)
        return RedirectResponse(
            url="/admin/seeds?error=An+unexpected+error+occurred",
            status_code=303,
        )


@router.post("/seeds/delete")
async def delete_seed(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/seeds?error=Invalid+request")
    try:
        await crawler_delete_seed(url)
        return RedirectResponse(
            url=f"/admin/seeds?success={quote('Seed deleted', safe='')}",
            status_code=303,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(exc), safe='')}",
            status_code=303,
        )
    except Exception:
        logger.exception("Failed to delete seed %s", url)
        return RedirectResponse(
            url="/admin/seeds?error=An+unexpected+error+occurred",
            status_code=303,
        )


@router.post("/seeds/import-tranco")
async def import_tranco(
    request: Request,
    count: str = Form(default="100"),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/seeds?error=Invalid+request")
    try:
        count_value = _parse_tranco_count(count)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(exc), safe='')}",
            status_code=303,
        )

    try:
        added = await import_tranco_seeds(count_value)
        return RedirectResponse(
            url=f"/admin/seeds?success={quote(f'Imported {added} seeds from Tranco top {count_value}', safe='')}",
            status_code=303,
        )
    except Exception:
        logger.exception("Failed to import Tranco seeds")
        return RedirectResponse(
            url="/admin/seeds?error=An+unexpected+error+occurred",
            status_code=303,
        )


@router.post("/queue")
async def add_to_queue(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/queue?error=Invalid+request")
    try:
        await enqueue_url(url)
        return RedirectResponse(
            url=f"/admin/queue?success={quote(f'Added {url} to queue', safe='')}",
            status_code=303,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/queue?error={quote(str(exc), safe='')}",
            status_code=303,
        )
    except Exception:
        logger.exception("Failed to enqueue URL %s", url)
        return RedirectResponse(
            url="/admin/queue?error=An+unexpected+error+occurred",
            status_code=303,
        )


@router.get("/analytics")
async def analytics_page(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
    analytics = get_analytics_data()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/analytics.html",
        {
            "request": request,
            "analytics": analytics,
            "csrf_token": csrf_token,
        },
    )


@router.get("/api-keys")
async def api_keys_list(_auth: None = Depends(require_admin_session_api)):
    return JSONResponse({"keys": list_api_keys()})


@router.post("/api-keys")
async def api_keys_create(
    request: Request, _auth: None = Depends(require_admin_session_api)
):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)

    rate_limit = body.get("rate_limit_daily")
    key_info = create_api_key(name, rate_limit)
    return JSONResponse(key_info, status_code=201)


@router.delete("/api-keys/{key_id}")
async def api_keys_revoke(
    key_id: str, _auth: None = Depends(require_admin_session_api)
):
    if revoke_api_key(key_id):
        return JSONResponse({"status": "revoked"})
    return JSONResponse({"error": "Key not found or already revoked"}, status_code=404)


router.include_router(crawlers_router)
router.include_router(indexer_router)
