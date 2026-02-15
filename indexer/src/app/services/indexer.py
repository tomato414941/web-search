"""Indexer Service - handles page indexing with custom search engine and embeddings."""

import asyncio
import logging

from app.core.config import settings
from shared.db.search import get_connection, is_postgres_mode, sql_placeholder
from shared.search import SearchIndexer
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", " ")


def _sanitize_outlinks(outlinks: list[str] | None) -> list[str]:
    if not outlinks:
        return []
    cleaned: list[str] = []
    for outlink in outlinks:
        if not outlink:
            continue
        cleaned.append(outlink.replace("\x00", ""))
    return cleaned


class IndexerService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self.search_indexer = SearchIndexer(db_path)

    async def index_page(
        self,
        url: str,
        title: str,
        content: str,
        outlinks: list[str] | None = None,
    ):
        """Index a single page into the database (async for embedding)."""
        safe_title = _sanitize_text(title)
        safe_content = _sanitize_text(content)
        safe_outlinks = _sanitize_outlinks(outlinks)

        conn = get_connection(self.db_path)
        try:
            # Index using custom search engine (inverted index)
            self.search_indexer.index_document(url, safe_title, safe_content, conn)

            # Save outlinks to link graph
            if safe_outlinks:
                self._save_links(conn, url, safe_outlinks)

            # Update global stats periodically (every index for now, optimize later)
            self.search_indexer.update_global_stats(conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB Error indexing {url}: {e}")
            raise
        finally:
            conn.close()

        if settings.OPENAI_API_KEY:
            try:
                vector_blob = await asyncio.wait_for(
                    embedding_service.embed(safe_content),
                    timeout=max(1, settings.OPENAI_EMBED_TIMEOUT_SEC),
                )
                if vector_blob:
                    self._save_embedding(url, vector_blob)
            except asyncio.TimeoutError:
                logger.warning("Embedding timed out for %s", url)
            except Exception as embed_error:
                logger.warning("Embedding failed for %s: %s", url, embed_error)

        logger.info("Indexed: %s", url)

    def _save_links(self, conn, src_url: str, outlinks: list[str]) -> None:
        """Save outlinks to the links table."""
        ph = sql_placeholder()
        cur = conn.cursor()
        savepoint = "sp_save_links"
        try:
            cur.execute(f"SAVEPOINT {savepoint}")
            # Remove old links from this page
            cur.execute(f"DELETE FROM links WHERE src = {ph}", (src_url,))
            # Insert new links (skip self-links)
            for dst in outlinks:
                if dst != src_url:
                    if is_postgres_mode():
                        cur.execute(
                            f"INSERT INTO links (src, dst) VALUES ({ph}, {ph}) "
                            "ON CONFLICT DO NOTHING",
                            (src_url, dst),
                        )
                    else:
                        cur.execute(
                            f"INSERT OR IGNORE INTO links (src, dst) VALUES ({ph}, {ph})",
                            (src_url, dst),
                        )
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception as e:
            logger.warning(f"Failed to save links for {src_url}: {e}")
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                cur.execute(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                logger.exception("Failed to rollback savepoint for links: %s", src_url)
                raise
        finally:
            cur.close()

    def _save_embedding(self, url: str, vector_blob: bytes) -> None:
        ph = sql_placeholder()
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            try:
                cur.execute(f"DELETE FROM page_embeddings WHERE url={ph}", (url,))
                cur.execute(
                    f"INSERT INTO page_embeddings (url, embedding) VALUES ({ph}, {ph})",
                    (url, vector_blob),
                )
            finally:
                cur.close()
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning("Failed to store embedding for %s: %s", url, e)
        finally:
            conn.close()

    def get_index_stats(self):
        """Get indexing statistics."""
        try:
            conn = get_connection(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM documents")
            total = cur.fetchone()[0]
            cur.close()
            conn.close()
            return {"total": total}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"total": 0}


# Global instance
indexer_service = IndexerService()
