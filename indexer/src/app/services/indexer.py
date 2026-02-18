"""Indexer Service - handles page indexing with custom search engine and embeddings."""

import asyncio
import logging
import os

from app.core.config import settings
from shared.db.search import get_connection, is_postgres_mode, sql_placeholder
from shared.embedding import deserialize, to_pgvector
from shared.search import SearchIndexer
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)

STATS_UPDATE_INTERVAL = int(os.getenv("STATS_UPDATE_INTERVAL", "10000"))


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
        self._pages_since_stats_update = 0
        self._stats_update_interval = STATS_UPDATE_INTERVAL

    async def index_page(
        self,
        url: str,
        title: str,
        content: str,
        outlinks: list[str] | None = None,
        *,
        skip_embedding: bool = False,
    ):
        """Index a single page into the database.

        Args:
            skip_embedding: If True, skip per-page embedding (for batch mode).
        """
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

            # Update global stats periodically (every N pages)
            self._pages_since_stats_update += 1
            if self._pages_since_stats_update >= self._stats_update_interval:
                self.search_indexer.update_global_stats(conn)
                self._pages_since_stats_update = 0
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB Error indexing {url}: {e}")
            raise
        finally:
            conn.close()

        embedded = False
        if not skip_embedding and settings.OPENAI_API_KEY:
            try:
                vector_blob = await asyncio.wait_for(
                    embedding_service.embed(safe_content),
                    timeout=max(1, settings.OPENAI_EMBED_TIMEOUT_SEC),
                )
                if vector_blob:
                    self._save_embedding(url, vector_blob)
                    embedded = True
            except asyncio.TimeoutError:
                logger.warning("Embedding timed out for %s", url)
            except Exception as embed_error:
                logger.warning("Embedding failed for %s: %s", url, embed_error)

        if skip_embedding:
            logger.info("Indexed (no embed): %s", url)
        elif embedded:
            logger.info("Indexed (embedded): %s", url)
        else:
            logger.info("Indexed (embed failed): %s", url)

    async def embed_and_save_batch(self, items: list[tuple[str, str]]) -> int:
        """Embed multiple (url, content) pairs in batch and save to DB.

        Returns number of embeddings saved.
        """
        if not items or not settings.OPENAI_API_KEY:
            return 0

        texts = [content for _, content in items]
        urls = [url for url, _ in items]

        try:
            blobs = await asyncio.wait_for(
                embedding_service.embed_batch(texts),
                timeout=max(10, settings.OPENAI_EMBED_TIMEOUT_SEC * 2),
            )
        except asyncio.TimeoutError:
            logger.warning("Batch embedding timed out for %d items", len(items))
            return 0
        except Exception as e:
            logger.warning("Batch embedding failed: %s", e)
            return 0

        saved = 0
        for url, blob in zip(urls, blobs):
            try:
                self._save_embedding(url, blob)
                saved += 1
            except Exception as e:
                logger.warning("Failed to save embedding for %s: %s", url, e)

        logger.info("Batch embedded %d/%d pages", saved, len(items))
        return saved

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
                    cur.execute(
                        f"INSERT INTO links (src, dst) VALUES ({ph}, {ph}) "
                        "ON CONFLICT DO NOTHING",
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
        conn = get_connection(self.db_path)
        try:
            self._upsert_embedding(conn, url, vector_blob)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning("Failed to store embedding for %s: %s", url, e)
        finally:
            conn.close()

    @staticmethod
    def _upsert_embedding(conn, url: str, vector_blob: bytes) -> None:
        ph = sql_placeholder()
        if is_postgres_mode():
            vec = deserialize(vector_blob)
            embedding_value = to_pgvector(vec)
        else:
            embedding_value = vector_blob

        cur = conn.cursor()
        try:
            cur.execute(
                f"""
                INSERT INTO page_embeddings (url, embedding) VALUES ({ph}, {ph})
                ON CONFLICT (url) DO UPDATE SET embedding = EXCLUDED.embedding
                """,
                (url, embedding_value),
            )
        finally:
            cur.close()

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
