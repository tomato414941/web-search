"""Content API Router - Full text content retrieval for indexed pages."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from frontend.api.deps import require_api_key
from frontend.api.middleware.rate_limiter import limiter
from shared.postgres.search import get_connection

router = APIRouter()


class ContentResponse(BaseModel):
    url: str = Field(description="Page URL")
    title: str | None = Field(default=None, description="Page title")
    content: str | None = Field(default=None, description="Full page text")
    word_count: int = Field(default=0, description="Word count")
    indexed_at: str | None = Field(
        default=None, description="When this page was last indexed (ISO 8601 UTC)"
    )
    published_at: str | None = Field(
        default=None, description="Original publication date (ISO 8601 UTC)"
    )


@router.get(
    "/content",
    response_model=ContentResponse,
    response_model_exclude_none=True,
    summary="Fetch stored page content by URL",
)
@limiter.limit("100/minute")
async def api_content(
    request,  # needed by limiter
    url: str,
    api_key_info: dict = Depends(require_api_key),
):
    """Retrieve full text content for a previously indexed URL.

    Requires API key authentication. Use this after searching to get
    the complete text of a page without re-crawling.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT title, content, word_count, indexed_at, published_at "
            "FROM documents WHERE url = %s",
            (url,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="URL not found in index")

    return ContentResponse(
        url=url,
        title=row[0],
        content=row[1],
        word_count=row[2] or 0,
        indexed_at=row[3].isoformat() if row[3] else None,
        published_at=row[4].isoformat() if row[4] else None,
    )
