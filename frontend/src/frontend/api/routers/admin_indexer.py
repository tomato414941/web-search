"""Indexer-focused admin routes."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from frontend.api.templates import templates
from frontend.core.config import settings
from frontend.services import admin_auth
from frontend.services.indexer_admin_client import fetch_indexer_health

router = APIRouter()

SESSION_COOKIE_NAME = admin_auth.SESSION_COOKIE_NAME
validate_session = admin_auth.validate_session


def _is_authenticated(request: Request) -> bool:
    return validate_session(request.cookies.get(SESSION_COOKIE_NAME))


@router.get("/indexer")
async def indexer_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    health = await fetch_indexer_health()
    return templates.TemplateResponse(
        request,
        "admin/indexer.html",
        {
            "request": request,
            "health": health,
            "indexer_url": settings.INDEXER_SERVICE_URL,
        },
    )
