"""Initial schema baseline.

Revision ID: 001
Revises:
Create Date: 2026-05-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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

    op.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            url TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            word_count INTEGER DEFAULT 0,
            indexed_at TIMESTAMP,
            published_at TIMESTAMP,
            updated_at TIMESTAMP,
            author TEXT,
            organization TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS page_ranks (
            url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
            score REAL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS information_origins (
            url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
            origin_type TEXT NOT NULL DEFAULT 'river',
            score REAL NOT NULL DEFAULT 0.5,
            inlink_count INTEGER DEFAULT 0,
            outlink_count INTEGER DEFAULT 0
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_info_origins_type "
        "ON information_origins(origin_type)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id SERIAL PRIMARY KEY,
            query TEXT NOT NULL,
            result_count INTEGER DEFAULT 0,
            search_mode TEXT DEFAULT 'default',
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_logs_created ON search_logs(created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs(query)")

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
            dedupe_key TEXT NOT NULL UNIQUE,
            published_at TEXT,
            author TEXT,
            organization TEXT
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

    op.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            domain TEXT NOT NULL,
            crawl_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_crawled_at INTEGER,
            is_seed BOOLEAN NOT NULL DEFAULT FALSE,
            discovered_via TEXT NOT NULL DEFAULT 'unknown'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_seed_created_at "
        "ON urls(created_at DESC) "
        "INCLUDE (url, domain, crawl_count, last_crawled_at) "
        "WHERE is_seed = TRUE"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS frontier_entries (
            url_hash TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            domain TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            discovered_at INTEGER NOT NULL,
            discovered_via TEXT NOT NULL,
            discovery_depth INTEGER NOT NULL DEFAULT 0,
            is_seed BOOLEAN NOT NULL DEFAULT FALSE,
            canonical_source TEXT,
            crawl_profile TEXT NOT NULL,
            priority_bucket SMALLINT NOT NULL,
            priority_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            next_fetch_at INTEGER NOT NULL,
            last_fetched_at INTEGER,
            last_success_at INTEGER,
            last_status TEXT,
            fail_streak INTEGER NOT NULL DEFAULT 0,
            lease_token TEXT,
            lease_expires_at INTEGER,
            etag TEXT,
            last_modified TEXT,
            content_hash TEXT,
            outlinks_last_discovered INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_frontier_ready "
        "ON frontier_entries "
        "(status, next_fetch_at, priority_bucket, priority_score DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_frontier_domain_ready "
        "ON frontier_entries(domain, status, next_fetch_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_frontier_profile_ready "
        "ON frontier_entries("
        "crawl_profile, next_fetch_at, priority_bucket, priority_score DESC, "
        "last_success_at, discovered_at, url_hash"
        ") WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_frontier_pending_planner_order "
        "ON frontier_entries("
        "priority_bucket, priority_score DESC, next_fetch_at, "
        "last_success_at ASC NULLS FIRST, discovered_at, url_hash"
        ") INCLUDE (url, domain, lease_expires_at) "
        "WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_frontier_profile_planner_order "
        "ON frontier_entries("
        "crawl_profile, priority_bucket, priority_score DESC, next_fetch_at, "
        "last_success_at ASC NULLS FIRST, discovered_at, url_hash"
        ") INCLUDE (url, domain, lease_expires_at) "
        "WHERE status = 'pending'"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS domain_state (
            domain TEXT PRIMARY KEY,
            next_request_at INTEGER NOT NULL DEFAULT 0,
            crawl_delay_sec DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            backoff_until INTEGER,
            fail_streak INTEGER NOT NULL DEFAULT 0,
            inflight_leases INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_domain_state_ready "
        "ON domain_state(backoff_until, next_request_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS crawl_logs (
            id SERIAL PRIMARY KEY,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            http_code INTEGER,
            error_message TEXT,
            created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::INTEGER,
            precheck_ms INTEGER,
            fetch_ms INTEGER,
            parse_ms INTEGER,
            submit_ms INTEGER,
            total_ms INTEGER,
            robots_ms INTEGER,
            ssrf_ms INTEGER,
            crawl_delay_ms INTEGER,
            fetch_request_ms INTEGER,
            fetch_body_read_ms INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_crawl_logs_url ON crawl_logs(url)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_logs_created ON crawl_logs(created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_logs_created_status "
        "ON crawl_logs(created_at, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_crawl_logs_status_created "
        "ON crawl_logs(status, created_at DESC)"
    )


def downgrade() -> None:
    for table in [
        "crawl_logs",
        "domain_state",
        "frontier_entries",
        "urls",
        "index_jobs",
        "search_events",
        "search_logs",
        "information_origins",
        "page_ranks",
        "documents",
        "domain_ranks",
        "links",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
