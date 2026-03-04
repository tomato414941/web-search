"""Indexer Service - handles page indexing and embeddings."""

import asyncio
import logging

from app.core.config import settings
from app.services.scoring import (
    compute_authorship_clarity,
    compute_content_quality,
    compute_temporal_anchor,
)
from shared.postgres.search import get_connection, sql_placeholder
from shared.embedding import deserialize, to_pgvector
from shared.search_kernel.indexer import SearchIndexer
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)

_os_client = None


def _get_opensearch_client():
    """Lazy-init OpenSearch client."""
    global _os_client
    if _os_client is None:
        from shared.opensearch.client import get_client
        from shared.opensearch.mapping import ensure_index

        _os_client = get_client(settings.OPENSEARCH_URL)
        ensure_index(_os_client)
    return _os_client


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
        published_at: str | None = None,
        author: str | None = None,
        organization: str | None = None,
        *,
        skip_embedding: bool = False,
    ):
        """Index a single page into the database."""
        safe_title = _sanitize_text(title)
        safe_content = _sanitize_text(content)
        safe_outlinks = _sanitize_outlinks(outlinks)

        conn = get_connection(self.db_path)
        try:
            # Write document metadata to documents table
            self.search_indexer.index_document(
                url, safe_title, safe_content, conn, published_at=published_at
            )

            # Save outlinks to link graph (always call to clear stale links)
            self._save_links(conn, url, safe_outlinks)

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

        # Dual-write to OpenSearch
        if settings.OPENSEARCH_ENABLED:
            self._index_to_opensearch(
                url,
                safe_title,
                safe_content,
                published_at=published_at,
                outlinks_count=len(safe_outlinks),
                author=author,
                organization=organization,
            )

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
            # Batch insert new links (skip self-links)
            pairs = [(src_url, dst) for dst in outlinks if dst != src_url]
            if pairs:
                cur.executemany(
                    f"INSERT INTO links (src, dst) VALUES ({ph}, {ph}) "
                    "ON CONFLICT DO NOTHING",
                    pairs,
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
        vec = deserialize(vector_blob)
        embedding_value = to_pgvector(vec)

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

    def _index_to_opensearch(
        self,
        url: str,
        title: str,
        content: str,
        published_at: str | None = None,
        outlinks_count: int = 0,
        author: str | None = None,
        organization: str | None = None,
    ) -> None:
        """Write document to OpenSearch (best-effort, logs on failure)."""
        try:
            from shared.opensearch.client import index_document
            from shared.search_kernel.analyzer import analyzer, STOP_WORDS

            title_tokens = analyzer.tokenize(title) if title else ""
            content_tokens = analyzer.tokenize(content) if content else ""
            word_count = (
                len(
                    [
                        t
                        for t in content_tokens.split()
                        if len(t) > 1 and t not in STOP_WORDS
                    ]
                )
                if content_tokens
                else 0
            )

            content_quality = compute_content_quality(
                word_count, outlinks_count, title, published_at
            )
            temporal_anchor = compute_temporal_anchor(published_at)
            authorship_clarity = compute_authorship_clarity(author, organization, url)

            from shared.search_kernel.factual_density import compute_factual_density

            factual_density = compute_factual_density(
                content, outlinks_count=outlinks_count, word_count=word_count
            )

            # Fetch origin score (replaces PageRank authority)
            origin_score, origin_type = self._get_origin_score(url)
            # Keep authority as fallback for documents not yet scored
            authority = self._get_authority(url)

            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).isoformat()

            client = _get_opensearch_client()
            index_document(
                client,
                url=url,
                title_tokens=title_tokens,
                content_tokens=content_tokens,
                word_count=word_count,
                indexed_at=now,
                authority=authority,
                published_at=published_at,
                content_quality=content_quality,
                temporal_anchor=temporal_anchor,
                authorship_clarity=authorship_clarity,
                factual_density=factual_density,
                origin_score=origin_score,
                origin_type=origin_type,
                author=author,
                organization=organization,
            )
        except Exception:
            logger.warning("OpenSearch index failed for %s", url, exc_info=True)

    def _get_authority(self, url: str) -> float:
        """Fetch max(page_rank, domain_rank) for a URL."""
        try:
            conn = get_connection(self.db_path)
            ph = sql_placeholder()
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT score FROM page_ranks WHERE url = {ph}", (url,))
                row = cur.fetchone()
                page_rank = row[0] if row else 0.0

                # Extract domain from URL
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
                cur.execute(
                    f"SELECT score FROM domain_ranks WHERE domain = {ph}",
                    (domain,),
                )
                row = cur.fetchone()
                domain_rank = row[0] if row else 0.0

                return max(page_rank, domain_rank)
            finally:
                cur.close()
                conn.close()
        except Exception:
            return 0.0

    def _get_origin_score(self, url: str) -> tuple[float, str]:
        """Fetch information origin score and type for a URL."""
        try:
            conn = get_connection(self.db_path)
            ph = sql_placeholder()
            cur = conn.cursor()
            try:
                cur.execute(
                    f"SELECT score, origin_type FROM information_origins WHERE url = {ph}",
                    (url,),
                )
                row = cur.fetchone()
                if row:
                    return float(row[0]), str(row[1])
                return 0.5, "river"
            finally:
                cur.close()
                conn.close()
        except Exception:
            return 0.5, "river"

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
