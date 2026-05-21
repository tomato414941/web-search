"""Admin Dashboard Router with Authentication."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from web_search_frontend.api.deps_admin import (
    require_admin_session,
    require_admin_session_api,
)
from web_search_frontend.api.middleware.rate_limiter import limiter
from web_search_frontend.api.routers.admin_crawlers import router as crawlers_router
from web_search_frontend.api.routers.admin_indexer import router as indexer_router
from web_search_frontend.api.templates import templates
from web_search_frontend.core.config import settings
from web_search_frontend.services.admin_auth import (
    CSRF_FORM_FIELD,
    SESSION_COOKIE_NAME,
    add_csrf_cookie,
    add_session_cookie,
    create_session,
    generate_csrf_token,
    get_csrf_token,
    validate_csrf_token,
)
from web_search_frontend.services.admin_dashboard import get_dashboard_data
from web_search_frontend.services.api_key import (
    create_api_key,
    list_api_keys,
    revoke_api_key,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _build_admin_redirect_url(
    path: str, *, success: str | None = None, error: str | None = None
) -> str:
    if success is not None:
        return f"{path}?success={quote(success, safe='')}"
    if error is not None:
        return f"{path}?error={quote(error, safe='')}"
    return path


def _redirect_admin(
    path: str, *, success: str | None = None, error: str | None = None
) -> RedirectResponse:
    return RedirectResponse(
        url=_build_admin_redirect_url(path, success=success, error=error),
        status_code=303,
    )


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
