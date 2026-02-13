"""Admin Dashboard Router with Authentication."""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services.admin_analytics import get_analytics_data
from frontend.services import admin_auth
from frontend.services.admin_dashboard import get_dashboard_data
from frontend.services.crawler_admin_client import (
    fetch_history,
    fetch_queue,
    fetch_seeds,
    find_crawler_url as _find_crawler_url,
    get_all_crawler_instances as _get_all_crawler_instances,
    get_crawler_instance_status as _get_crawler_instance_status,
    import_tranco as import_tranco_seeds,
    add_seed as crawler_add_seed,
    delete_seed as crawler_delete_seed,
    enqueue_url,
    start_crawler_instance,
    start_worker,
    stop_crawler_instance,
    stop_worker,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# Re-export for backward compatibility with existing tests/imports.
CSRF_COOKIE_NAME = admin_auth.CSRF_COOKIE_NAME
CSRF_FORM_FIELD = admin_auth.CSRF_FORM_FIELD
SESSION_COOKIE_NAME = admin_auth.SESSION_COOKIE_NAME
create_session = admin_auth.create_session
generate_csrf_token = admin_auth.generate_csrf_token
get_csrf_token = admin_auth.get_csrf_token
validate_csrf_token = admin_auth.validate_csrf_token
validate_session = admin_auth.validate_session
add_csrf_cookie = admin_auth.add_csrf_cookie
add_session_cookie = admin_auth.add_session_cookie


def _is_authenticated(request: Request) -> bool:
    return validate_session(request.cookies.get(SESSION_COOKIE_NAME))


def _parse_tranco_count(raw_count: str | None) -> int:
    normalized = (raw_count or "").strip().replace(",", "")
    if not normalized.isdigit():
        raise ValueError("Count must be an integer between 1 and 10000")

    count = int(normalized)
    if count < 1 or count > 10000:
        raise ValueError("Count must be between 1 and 10000")
    return count


async def get_crawler_instance_status(url: str) -> dict:
    return await _get_crawler_instance_status(url)


async def get_all_crawler_instances() -> list[dict]:
    return await _get_all_crawler_instances(settings.CRAWLER_INSTANCES)


def find_crawler_url(name: str) -> str | None:
    return _find_crawler_url(name, settings.CRAWLER_INSTANCES)


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
async def dashboard(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

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
async def seeds_page(request: Request, success: str = "", error: str = ""):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    seeds = await fetch_seeds()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/seeds.html",
        {
            "request": request,
            "seeds": seeds,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
        },
    )


@router.get("/queue")
async def queue_page(request: Request, success: str = "", error: str = ""):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    queue_urls = await fetch_queue(limit=50)
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/queue.html",
        {
            "request": request,
            "queue_urls": queue_urls,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
        },
    )


@router.get("/history")
async def history_page(request: Request, url: str = ""):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

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
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/seeds?error=Invalid+request", status_code=303
        )

    try:
        await crawler_add_seed(url)
        return RedirectResponse(
            url=f"/admin/seeds?success={quote(f'Added seed {url}', safe='')}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(exc), safe='')}",
            status_code=303,
        )


@router.post("/seeds/delete")
async def delete_seed(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/seeds?error=Invalid+request", status_code=303
        )

    try:
        await crawler_delete_seed(url)
        return RedirectResponse(
            url=f"/admin/seeds?success={quote('Seed deleted', safe='')}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(exc), safe='')}",
            status_code=303,
        )


@router.post("/seeds/import-tranco")
async def import_tranco(
    request: Request,
    count: str = Form(default="100"),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/seeds?error=Invalid+request", status_code=303
        )

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
    except Exception as exc:
        return RedirectResponse(
            url=f"/admin/seeds?error={quote(str(exc), safe='')}",
            status_code=303,
        )


@router.post("/queue")
async def add_to_queue(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/queue?error=Invalid+request", status_code=303
        )

    try:
        await enqueue_url(url)
        return RedirectResponse(
            url=f"/admin/queue?success={quote(f'Added {url} to queue', safe='')}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"/admin/queue?error={quote(str(exc), safe='')}",
            status_code=303,
        )


@router.post("/crawler/start")
async def crawler_start(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/", status_code=303)

    await start_worker()
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/crawler/stop")
async def crawler_stop(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/", status_code=303)

    await stop_worker()
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/analytics")
async def analytics_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

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


@router.get("/crawlers")
async def crawlers_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    instances = await get_all_crawler_instances()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/crawlers.html",
        {
            "request": request,
            "instances": instances,
            "csrf_token": csrf_token,
        },
    )


@router.post("/crawlers/{name}/start")
async def crawler_instance_start(
    request: Request,
    name: str,
    concurrency: int = Form(default=1),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    await start_crawler_instance(url, concurrency)
    return RedirectResponse(url="/admin/crawlers", status_code=303)


@router.post("/crawlers/{name}/stop")
async def crawler_instance_stop(
    request: Request,
    name: str,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    await stop_crawler_instance(url)
    return RedirectResponse(url="/admin/crawlers", status_code=303)
