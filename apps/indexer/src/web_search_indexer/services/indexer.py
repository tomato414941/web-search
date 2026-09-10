"""Indexer service for baseline document and OpenSearch indexing."""

import asyncio
from dataclasses import dataclass
import logging

from web_search_indexer.core.config import settings
from web_search_postgres import get_connection
from web_search_indexer.services.document_indexer import SearchIndexer
from web_search_indexer.services.opensearch_document import build_search_index_document
from web_search_opensearch.document import SearchIndexDocument

logger = logging.getLogger(__name__)

_os_client = None


class OpenSearchIndexingError(RuntimeError):
    pass


def _get_opensearch_client():
    """Lazy-init OpenSearch client."""
    global _os_client
    if _os_client is None:
        from web_search_opensearch.client import get_client
        from web_search_opensearch.mapping import ensure_index

        client = get_client(settings.OPENSEARCH_URL)
        ensure_index(client)
        _os_client = client
    return _os_client


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", " ")


@dataclass(slots=True)
class IndexedPage:
    url: str
    title: str
    content: str


class IndexerService:
    def __init__(self):
        self.search_indexer = SearchIndexer()

    async def index_page(
        self,
        url: str,
        title: str,
        content: str,
    ) -> IndexedPage:
        """Index a single page into the baseline document store."""
        safe_title = _sanitize_text(title)
        safe_content = _sanitize_text(content)

        await asyncio.to_thread(
            self._write_document,
            url,
            safe_title,
            safe_content,
        )

        page = IndexedPage(
            url=url,
            title=safe_title,
            content=safe_content,
        )

        await asyncio.to_thread(self._index_to_opensearch_page, page)

        logger.info("Indexed: %s", url)

        return page

    def _write_document(
        self,
        url: str,
        title: str,
        content: str,
    ) -> None:
        conn = get_connection()
        try:
            self.search_indexer.index_document(url, title, content, conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("DB Error indexing %s: %s", url, e)
            raise
        finally:
            conn.close()

    def _index_to_opensearch_page(self, page: IndexedPage) -> None:
        from web_search_opensearch.client import delete_document, index_document

        try:
            doc = self._build_search_index_document(page)
            client = _get_opensearch_client()
            if doc is None:
                delete_document(client, page.url)
                logger.info("Skipped OpenSearch index for excluded host: %s", page.url)
                return
            index_document(client, doc)
        except Exception:
            raise OpenSearchIndexingError(
                f"Hybrid indexing failed for {page.url}"
            ) from None

    def _build_search_index_document(
        self, page: IndexedPage
    ) -> SearchIndexDocument | None:
        return build_search_index_document(page)


# Global instance
indexer_service = IndexerService()
