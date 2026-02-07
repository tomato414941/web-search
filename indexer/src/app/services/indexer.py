"""Indexer Service - handles page indexing with custom search engine and embeddings."""

import logging

from app.core.config import settings
from shared.db.search import open_db, get_connection, is_postgres_mode
from shared.search import SearchIndexer
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)


def _placeholder() -> str:
    """Return the appropriate placeholder for the current database."""
    return "%s" if is_postgres_mode() else "?"


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
        try:
            # Open DB connection
            conn = open_db(self.db_path)

            # Index using custom search engine (inverted index)
            self.search_indexer.index_document(url, title, content, conn)
            conn.commit()

            # Save outlinks to link graph
            if outlinks:
                self._save_links(conn, url, outlinks)

            # Generate and store embedding (skip if no OpenAI key)
            if settings.OPENAI_API_KEY:
                try:
                    vector_blob = await embedding_service.embed(content)
                    if vector_blob:
                        ph = _placeholder()
                        cur = conn.cursor()
                        cur.execute(
                            f"DELETE FROM page_embeddings WHERE url={ph}", (url,)
                        )
                        cur.execute(
                            f"INSERT INTO page_embeddings (url, embedding) VALUES ({ph}, {ph})",
                            (url, vector_blob),
                        )
                        cur.close()
                        conn.commit()
                except Exception as embed_error:
                    # Don't fail indexing if embedding fails
                    logger.warning(f"Embedding failed for {url}: {embed_error}")

            # Update global stats periodically (every index for now, optimize later)
            self.search_indexer.update_global_stats(conn)
            conn.commit()

            conn.close()

            logger.info(f"Indexed: {url}")
        except Exception as e:
            logger.error(f"DB Error indexing {url}: {e}")
            raise

    def _save_links(self, conn, src_url: str, outlinks: list[str]) -> None:
        """Save outlinks to the links table."""
        ph = _placeholder()
        try:
            cur = conn.cursor()
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
            conn.commit()
            cur.close()
        except Exception as e:
            logger.warning(f"Failed to save links for {src_url}: {e}")

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
