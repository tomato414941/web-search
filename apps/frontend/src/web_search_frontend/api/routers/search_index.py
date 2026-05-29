from pydantic import BaseModel, Field
from fastapi import APIRouter

from web_search_frontend.services.search_index import get_indexed_document_count

router = APIRouter()


class SearchIndexDocumentSummary(BaseModel):
    total: int = Field(ge=0)


class SearchIndexResponse(BaseModel):
    documents: SearchIndexDocumentSummary


@router.get("/search-index", response_model=SearchIndexResponse)
async def search_index() -> SearchIndexResponse:
    return SearchIndexResponse(
        documents=SearchIndexDocumentSummary(total=get_indexed_document_count())
    )
