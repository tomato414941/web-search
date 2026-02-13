"""Crawler-focused admin routes."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services import admin_auth
from frontend.services.crawler_admin_client import (
    find_crawler_url as _find_crawler_url,
    get_all_crawler_instances as _get_all_crawler_instances,
    start_crawler_instance,
    start_worker,
    stop_crawler_instance,
    stop_worker,
)

router = APIRouter()

CSRF_FORM_FIELD = admin_auth.CSRF_FORM_FIELD
SESSION_COOKIE_NAME = admin_auth.SESSION_COOKIE_NAME
get_csrf_token = admin_auth.get_csrf_token
validate_csrf_token = admin_auth.validate_csrf_token
validate_session = admin_auth.validate_session


def _is_authenticated(request: Request) -> bool:
    return validate_session(request.cookies.get(SESSION_COOKIE_NAME))


async def get_all_crawler_instances() -> list[dict]:
    return await _get_all_crawler_instances(settings.CRAWLER_INSTANCES)


def find_crawler_url(name: str) -> str | None:
    return _find_crawler_url(name, settings.CRAWLER_INSTANCES)


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
