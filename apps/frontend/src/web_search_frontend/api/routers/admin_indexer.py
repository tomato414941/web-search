"""Indexer-focused admin routes."""

from fastapi import APIRouter, Depends, Request

from web_search_frontend.api.deps_admin import require_admin_session
from web_search_frontend.api.templates import templates
from web_search_frontend.services.indexer_admin_client import (
    get_indexer_admin_read_model,
)

router = APIRouter()


@router.get("/indexer")
async def indexer_page(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
    indexer_data = await get_indexer_admin_read_model()
    return templates.TemplateResponse(
        request,
        "admin/indexer.html",
        {
            "request": request,
            "health": indexer_data["health"],
            "snapshot_generated_at": indexer_data["snapshot_generated_at"],
            "snapshot_loaded_from": indexer_data["snapshot_loaded_from"],
        },
    )
