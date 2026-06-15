"""Indexer API router for crawler-submitted documents."""

import logging
import secrets
from fastapi import APIRouter, HTTPException, Header
from web_search_indexer.core.config import settings
from web_search_indexer.services.indexer import indexer_service
from web_search_contracts.indexer_api import IndexDocumentRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_api_key(x_api_key: str) -> None:
    """Verify API key from header."""
    if not secrets.compare_digest(x_api_key, settings.INDEXER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/documents")
async def index_document(
    page: IndexDocumentRequest, x_api_key: str = Header(..., alias="X-API-Key")
) -> dict:
    """Index a crawled page immediately."""
    verify_api_key(x_api_key)

    try:
        indexed = await indexer_service.index_page(
            url=str(page.url),
            title=page.title,
            content=page.content,
        )
        return {
            "ok": True,
            "indexed": True,
            "url": indexed.url,
        }
    except Exception as e:
        logger.error("Indexing failed for %s: %s", page.url, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Indexing failed")
