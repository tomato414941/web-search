"""Indexer Service - handles page indexing with FTS5 and embeddings."""

import logging
import sqlite3

from app.core.config import settings
from shared.db.search import open_db, upsert_page
from app.services.embedding import embedding_service
from app.services.analyzer import analyzer

logger = logging.getLogger(__name__)


class IndexerService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

    async def index_page(self, url: str, title: str, content: str):
        """Index a single page into the database (async for embedding)."""
        try:
            # Tokenize for FTS5
            idx_title = analyzer.tokenize(title)
            idx_content = analyzer.tokenize(content)

            # Open DB connection
            conn = open_db(self.db_path)

            # Insert into DB (upsert_page expects connection as first arg)
            upsert_page(conn, url, idx_title, idx_content, title, content)
            conn.commit()

            # Generate and store embedding (skip if no OpenAI key)
            if settings.OPENAI_API_KEY:
                try:
                    vector_blob = await embedding_service.embed(content)
                    if vector_blob:
                        conn.execute("DELETE FROM page_embeddings WHERE url=?", (url,))
                        conn.execute(
                            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)",
                            (url, vector_blob),
                        )
                        conn.commit()
                except Exception as embed_error:
                    # Don't fail indexing if embedding fails
                    logger.warning(f"Embedding failed for {url}: {embed_error}")

            conn.close()

            logger.info(f"Indexed: {url}")
        except Exception as e:
            logger.error(f"DB Error indexing {url}: {e}")
            raise

    def get_index_stats(self):
        """Get indexing statistics."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            total = cursor.fetchone()[0]
            conn.close()
            return {"total": total}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"total": 0}


# Global instance
indexer_service = IndexerService()
