"""Indexer Service - handles page indexing with custom search engine and embeddings."""

import logging
import sqlite3

from app.core.config import settings
from shared.db.search import open_db, upsert_page
from shared.search import SearchIndexer
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)


class IndexerService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self.search_indexer = SearchIndexer(db_path)

    async def index_page(self, url: str, title: str, content: str):
        """Index a single page into the database (async for embedding)."""
        try:
            # Open DB connection
            conn = open_db(self.db_path)

            # 1. Index using new custom search engine (inverted index)
            self.search_indexer.index_document(url, title, content, conn)

            # 2. Also index to FTS5 for backward compatibility (during migration)
            from shared.analyzer import analyzer
            idx_title = analyzer.tokenize(title)
            idx_content = analyzer.tokenize(content)
            upsert_page(conn, url, idx_title, idx_content, title, content)

            conn.commit()

            # 3. Generate and store embedding (skip if no OpenAI key)
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

            # 4. Update global stats periodically (every index for now, optimize later)
            self.search_indexer.update_global_stats(conn)
            conn.commit()

            conn.close()

            logger.info(f"Indexed: {url}")
        except Exception as e:
            logger.error(f"DB Error indexing {url}: {e}")
            raise

    def get_index_stats(self):
        """Get indexing statistics."""
        try:
            conn = sqlite3.connect(self.db_path)
            # Use new documents table for stats
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            total_new = cursor.fetchone()[0]
            # Also get FTS5 count for comparison
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            total_fts5 = cursor.fetchone()[0]
            conn.close()
            return {
                "total": total_new,
                "total_fts5": total_fts5,  # For migration monitoring
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"total": 0}


# Global instance
indexer_service = IndexerService()
