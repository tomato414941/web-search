"""Indexer-focused admin routes."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services import admin_auth
from frontend.services.indexer_admin_client import (
    fetch_failed_jobs,
    fetch_indexer_stats,
    retry_failed_job,
)

router = APIRouter()

SESSION_COOKIE_NAME = admin_auth.SESSION_COOKIE_NAME
CSRF_FORM_FIELD = admin_auth.CSRF_FORM_FIELD
validate_session = admin_auth.validate_session
validate_csrf_token = admin_auth.validate_csrf_token
get_csrf_token = admin_auth.get_csrf_token


def _is_authenticated(request: Request) -> bool:
    return validate_session(request.cookies.get(SESSION_COOKIE_NAME))


@router.get("/indexer")
async def indexer_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    health = await fetch_indexer_stats()
    failed_jobs = await fetch_failed_jobs(limit=50)
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
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not validate_csrf_token(request, csrf_token):
        return RedirectResponse(
            url="/admin/indexer?error=Invalid+request", status_code=303
        )

    await retry_failed_job(job_id)
    return RedirectResponse(url="/admin/indexer", status_code=303)
