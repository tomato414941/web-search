"""Indexer service for baseline document and OpenSearch indexing."""

import asyncio
from dataclasses import dataclass
import logging

from web_search_indexer.core.config import settings
from web_search_postgres import get_connection
from web_search_indexer.services.document_indexer import SearchIndexer
from web_search_indexer.services.opensearch_document import build_opensearch_document
from web_search_postgres.repositories import DocumentRepository

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

        _os_client = get_client(settings.OPENSEARCH_URL)
        ensure_index(_os_client)
    return _os_client


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", " ")


@dataclass(slots=True)
class IndexedPage:
    url: str
    title: str
    content: str
    outlinks_count: int


class IndexerService:
    def __init__(self):
        self.search_indexer = SearchIndexer()

    async def index_page(
        self,
        url: str,
        title: str,
        content: str,
        outlinks_count: int = 0,
        *,
        skip_opensearch: bool = False,
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
            outlinks_count=max(0, outlinks_count),
        )

        if settings.OPENSEARCH_ENABLED and not skip_opensearch:
            await asyncio.to_thread(self._index_to_opensearch_page, page)

        logger.info("Indexed: %s", url)

        return page

    async def index_pages_to_opensearch(self, pages: list[IndexedPage]) -> int:
        if not settings.OPENSEARCH_ENABLED or not pages:
            return 0
        return await asyncio.to_thread(self._index_pages_to_opensearch_sync, pages)

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

    def _index_to_opensearch(
        self,
        url: str,
        title: str,
        content: str,
        outlinks_count: int = 0,
    ) -> None:
        page = IndexedPage(
            url=url,
            title=title,
            content=content,
            outlinks_count=outlinks_count,
        )
        self._index_to_opensearch_page(page)

    def _index_to_opensearch_page(self, page: IndexedPage) -> None:
        from web_search_opensearch.client import delete_document, index_document

        try:
            doc = self._build_opensearch_document(page)
            client = _get_opensearch_client()
            if doc is None:
                delete_document(client, page.url)
                logger.info("Skipped OpenSearch index for excluded host: %s", page.url)
                return
            index_document(client, **doc)
        except Exception:
            logger.warning("OpenSearch index failed for %s", page.url, exc_info=True)

    def _index_pages_to_opensearch_sync(self, pages: list[IndexedPage]) -> int:
        from web_search_opensearch.client import bulk_index, delete_document

        client = _get_opensearch_client()
        docs: list[dict[str, object]] = []
        build_failures: list[str] = []
        for page in pages:
            try:
                doc = self._build_opensearch_document(page)
            except Exception:
                build_failures.append(page.url)
                logger.warning(
                    "Failed to build OpenSearch document for %s",
                    page.url,
                    exc_info=True,
                )
                continue
            if doc is None:
                delete_document(client, page.url)
                logger.info("Skipped OpenSearch index for excluded host: %s", page.url)
                continue
            docs.append(doc)

        if build_failures:
            raise OpenSearchIndexingError(
                f"Failed to build OpenSearch documents for {len(build_failures)} pages"
            )

        if not docs:
            return 0

        try:
            indexed = bulk_index(client, docs)
            if indexed != len(docs):
                raise OpenSearchIndexingError(
                    f"OpenSearch bulk indexed {indexed}/{len(docs)} pages"
                )
            logger.info("Bulk indexed %d/%d pages to OpenSearch", indexed, len(docs))
            return indexed
        except Exception:
            logger.warning("OpenSearch bulk index failed", exc_info=True)
            raise

    def _build_opensearch_document(self, page: IndexedPage) -> dict[str, object] | None:
        page_rank, domain_rank = self._get_link_ranks(page.url)
        return build_opensearch_document(
            page,
            page_rank=page_rank,
            domain_rank=domain_rank,
        )

    def _get_link_ranks(self, url: str) -> tuple[float, float]:
        """Fetch page-level and domain-level link ranks for a URL."""
        try:
            return DocumentRepository.fetch_link_ranks(url)
        except Exception:
            return 0.0, 0.0


# Global instance
indexer_service = IndexerService()
