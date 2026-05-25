"""Crawler-focused admin routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from web_search_frontend.api.deps_admin import (
    check_csrf_or_redirect,
    require_admin_session,
)
from web_search_frontend.api.templates import templates
from web_search_frontend.core.config import settings
from web_search_frontend.services.admin_auth import CSRF_FORM_FIELD
from web_search_frontend.services.admin_dashboard import clear_dashboard_cache
from web_search_frontend.services.crawler_admin_client import (
    start_worker,
    stop_worker,
)
from web_search_frontend.services.crawler_instances import (
    clear_crawler_instances_cache,
    get_crawler_instances_read_model as _get_crawler_instances_read_model,
)

router = APIRouter()


async def get_crawler_instances_read_model() -> dict:
    return await _get_crawler_instances_read_model(settings.CRAWLER_INSTANCES)


@router.post("/crawler/start")
async def crawler_start(
    request: Request,
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/")
    await start_worker()
    clear_dashboard_cache()
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
    clear_dashboard_cache()
    clear_crawler_instances_cache()
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/crawlers")
async def crawlers_page(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
    crawler_read_model = await get_crawler_instances_read_model()
    return templates.TemplateResponse(
        request,
        "admin/crawlers.html",
        {
            "request": request,
            "instances": crawler_read_model["instances"],
            "snapshot_generated_at": crawler_read_model["snapshot_generated_at"],
            "snapshot_loaded_from": crawler_read_model["snapshot_loaded_from"],
        },
    )
