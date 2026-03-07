"""Crawler-focused admin routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from frontend.api.deps_admin import check_csrf_or_redirect, require_admin_session
from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services.admin_auth import CSRF_FORM_FIELD, get_csrf_token
from frontend.services.crawler_admin_client import (
    clear_crawler_instances_cache,
    find_crawler_url as _find_crawler_url,
    get_all_crawler_instances as _get_all_crawler_instances,
    start_crawler_instance,
    start_worker,
    stop_crawler_instance,
    stop_worker,
)

router = APIRouter()


async def get_all_crawler_instances() -> list[dict]:
    return await _get_all_crawler_instances(settings.CRAWLER_INSTANCES)


def find_crawler_url(name: str) -> str | None:
    return _find_crawler_url(name, settings.CRAWLER_INSTANCES)


@router.post("/crawler/start")
async def crawler_start(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/")
    await start_worker()
    clear_crawler_instances_cache()
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/crawler/stop")
async def crawler_stop(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/")
    await stop_worker()
    clear_crawler_instances_cache()
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/crawlers")
async def crawlers_page(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
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
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/crawlers")
    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    await start_crawler_instance(url, concurrency)
    clear_crawler_instances_cache()
    return RedirectResponse(url="/admin/crawlers", status_code=303)


@router.post("/crawlers/{name}/stop")
async def crawler_instance_stop(
    request: Request,
    name: str,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/crawlers")
    url = find_crawler_url(name)
    if not url:
        return RedirectResponse(url="/admin/crawlers", status_code=303)

    await stop_crawler_instance(url)
    clear_crawler_instances_cache()
    return RedirectResponse(url="/admin/crawlers", status_code=303)
