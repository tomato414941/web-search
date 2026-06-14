"""Content API Router - Full text content retrieval for indexed pages."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from web_search_frontend.api.middleware.rate_limiter import limiter
from web_search_frontend.services.db_helpers import db_cursor
from web_search_postgres.repositories.document_repo import DocumentRepository

router = APIRouter()


class ContentResponse(BaseModel):
    url: str = Field(description="Page URL")
    title: str | None = Field(default=None, description="Page title")
    content: str | None = Field(default=None, description="Full page text")
    indexed_at: str | None = Field(
        default=None, description="When this page was last indexed (ISO 8601 UTC)"
    )
    published_at: str | None = Field(
        default=None, description="Original publication date (ISO 8601 UTC)"
    )


@router.get(
    "/indexed-documents/by-url",
    response_model=ContentResponse,
    response_model_exclude_none=True,
    summary="Fetch stored page content by URL",
)
@limiter.limit("100/minute")
async def api_content(
    request: Request,  # needed by limiter
    url: str,
):
    """Retrieve full text content for a previously indexed URL.

    Use this after searching to get the complete text of a page without
    re-crawling.
    """
    with db_cursor() as (conn, _):
        row = DocumentRepository.fetch_by_url(conn, url)

    if not row:
        raise HTTPException(status_code=404, detail="URL not found in index")

    return ContentResponse(
        url=url,
        title=row[0],
        content=row[1],
        indexed_at=row[2].isoformat() if row[2] else None,
        published_at=row[3].isoformat() if row[3] else None,
    )
