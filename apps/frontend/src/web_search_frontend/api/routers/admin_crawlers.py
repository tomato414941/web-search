"""Crawler-focused admin routes."""

from fastapi import APIRouter, Depends, Request

from web_search_frontend.api.deps_admin import require_admin_session
from web_search_frontend.api.templates import templates
from web_search_frontend.core.config import settings
from web_search_frontend.services.crawler_instances import (
    get_crawler_instances_read_model as _get_crawler_instances_read_model,
)

router = APIRouter()


async def get_crawler_instances_read_model() -> dict:
    return await _get_crawler_instances_read_model(settings.CRAWLER_INSTANCES)


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
