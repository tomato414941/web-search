"""Initial schema: all tables, indexes, and extensions.

Consolidates the previous custom migrations (001-004) plus crawler tables
into a single Alembic baseline.

Revision ID: 001
Revises:
Create Date: 2026-02-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -- Link Graph --
    op.execute("""
        CREATE TABLE IF NOT EXISTS links (
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            PRIMARY KEY (src, dst)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_links_src ON links(src)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS domain_ranks (
            domain TEXT PRIMARY KEY,
            score REAL NOT NULL
        )
    """)

    # -- Document & Search Index --
    op.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            url TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            word_count INTEGER DEFAULT 0,
            indexed_at TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS page_ranks (
            url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
            score REAL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS page_embeddings (
            url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
            embedding vector(1536)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_page_embeddings_hnsw
            ON page_embeddings USING hnsw (embedding vector_cosine_ops)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS inverted_index (
            token TEXT NOT NULL,
            url TEXT NOT NULL REFERENCES documents(url) ON DELETE CASCADE,
            field TEXT NOT NULL,
            term_freq INTEGER DEFAULT 1,
            PRIMARY KEY (token, url, field)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_inverted_token ON inverted_index(token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inverted_url ON inverted_index(url)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS index_stats (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS token_stats (
            token TEXT PRIMARY KEY,
            doc_freq INTEGER DEFAULT 0
        )
    """)

    # -- Search Analytics --
    op.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id SERIAL PRIMARY KEY,
            query TEXT NOT NULL,
            result_count INTEGER DEFAULT 0,
            search_mode TEXT DEFAULT 'default',
            user_agent TEXT,
            api_key_id TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_logs_created ON search_logs(created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs(query)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_logs_api_key ON search_logs(api_key_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS search_events (
            id SERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            query TEXT NOT NULL,
            query_norm TEXT NOT NULL,
            request_id TEXT,
            session_hash TEXT,
            result_count INTEGER,
            clicked_url TEXT,
            clicked_rank INTEGER,
            latency_ms INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_events_created "
        "ON search_events(created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_events_type_created "
        "ON search_events(event_type, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_events_query_created "
        "ON search_events(query_norm, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_events_request_id "
        "ON search_events(request_id)"
    )

    # -- Indexer Job Queue --
    op.execute("""
        CREATE TABLE IF NOT EXISTS index_jobs (
            job_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            outlinks JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 5,
            available_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
            lease_until BIGINT,
            worker_id TEXT,
            last_error TEXT,
            created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
            updated_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
            content_hash TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_index_jobs_status_available "
        "ON index_jobs(status, available_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_index_jobs_status_lease "
        "ON index_jobs(status, lease_until)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_index_jobs_created ON index_jobs(created_at)"
    )

    # -- API Keys --
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            name TEXT NOT NULL,
            rate_limit_daily INTEGER NOT NULL DEFAULT 1000,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status)")

    # -- Crawler: URLs --
    op.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority REAL NOT NULL DEFAULT 0,
            crawl_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_crawled_at INTEGER,
            is_seed BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_pending "
        "ON urls(priority DESC) WHERE status = 'pending'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_recrawl "
        "ON urls(last_crawled_at) WHERE status IN ('done', 'failed')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_pending_claim "
        "ON urls(status, priority DESC, created_at) WHERE status = 'pending'"
    )

    # -- Crawler: Crawl Logs --
    op.execute("""
        CREATE TABLE IF NOT EXISTS crawl_logs (
            id SERIAL PRIMARY KEY,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            http_code INTEGER,
            error_message TEXT,
            created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_crawl_logs_url ON crawl_logs(url)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_logs_created ON crawl_logs(created_at)"
    )


def downgrade() -> None:
    for table in [
        "crawl_logs",
        "urls",
        "api_keys",
        "index_jobs",
        "search_events",
        "search_logs",
        "token_stats",
        "index_stats",
        "inverted_index",
        "page_embeddings",
        "page_ranks",
        "documents",
        "domain_ranks",
        "links",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
