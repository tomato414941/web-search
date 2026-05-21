"""Indexer-focused admin routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from web_search_frontend.api.deps_admin import (
    check_csrf_or_redirect,
    require_admin_session,
)
from web_search_frontend.api.templates import templates
from web_search_frontend.core.config import settings
from web_search_frontend.services.admin_auth import CSRF_FORM_FIELD, get_csrf_token
from web_search_frontend.services.indexer_admin_client import (
    get_indexer_admin_read_model,
    retry_failed_job,
)

router = APIRouter()


@router.get("/indexer")
async def indexer_page(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
    indexer_data = await get_indexer_admin_read_model()
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/indexer.html",
        {
            "request": request,
            "health": indexer_data["health"],
            "indexer_url": settings.INDEXER_SERVICE_URL,
            "failed_jobs": indexer_data["failed_jobs"],
            "snapshot_generated_at": indexer_data["snapshot_generated_at"],
            "snapshot_loaded_from": indexer_data["snapshot_loaded_from"],
            "csrf_token": csrf_token,
        },
    )


@router.post("/indexer/retry-job")
async def retry_job(
    request: Request,
    job_id: str = Form(...),
    csrf_token: str = Form(None, alias=CSRF_FORM_FIELD),
    _auth: None = Depends(require_admin_session),
):
    check_csrf_or_redirect(request, csrf_token, "/admin/indexer?error=Invalid+request")
    await retry_failed_job(job_id)
    return RedirectResponse(url="/admin/indexer", status_code=303)
