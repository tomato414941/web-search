"""Indexer-focused admin routes."""

import asyncio

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from frontend.api.deps_admin import check_csrf_or_redirect, require_admin_session
from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services.admin_auth import CSRF_FORM_FIELD, get_csrf_token
from frontend.services.indexer_admin_client import (
    fetch_failed_jobs,
    fetch_indexer_stats,
    retry_failed_job,
)

router = APIRouter()


@router.get("/indexer")
async def indexer_page(
    request: Request,
    _auth: None = Depends(require_admin_session),
):
    health, failed_jobs = await asyncio.gather(
        fetch_indexer_stats(),
        fetch_failed_jobs(limit=50),
    )
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "admin/indexer.html",
        {
            "request": request,
            "health": health,
            "indexer_url": settings.INDEXER_SERVICE_URL,
            "failed_jobs": failed_jobs,
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
