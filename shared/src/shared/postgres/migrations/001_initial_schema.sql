-- Initial schema: all tables and indexes
-- For existing databases, this migration is marked as applied automatically.

CREATE EXTENSION IF NOT EXISTS vector;

-- Link Graph
CREATE TABLE IF NOT EXISTS links (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);

CREATE TABLE IF NOT EXISTS domain_ranks (
  domain TEXT PRIMARY KEY,
  score REAL NOT NULL
);

-- Document & Search Index
CREATE TABLE IF NOT EXISTS documents (
  url TEXT PRIMARY KEY,
  title TEXT,
  content TEXT,
  word_count INTEGER DEFAULT 0,
  indexed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS page_ranks (
  url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
  score REAL
);

CREATE TABLE IF NOT EXISTS page_embeddings (
  url TEXT PRIMARY KEY REFERENCES documents(url) ON DELETE CASCADE,
  embedding vector(1536)
);
CREATE INDEX IF NOT EXISTS idx_page_embeddings_hnsw
  ON page_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS inverted_index (
  token TEXT NOT NULL,
  url TEXT NOT NULL REFERENCES documents(url) ON DELETE CASCADE,
  field TEXT NOT NULL,
  term_freq INTEGER DEFAULT 1,
  positions TEXT,
  PRIMARY KEY (token, url, field)
);
CREATE INDEX IF NOT EXISTS idx_inverted_token ON inverted_index(token);
CREATE INDEX IF NOT EXISTS idx_inverted_url ON inverted_index(url);

CREATE TABLE IF NOT EXISTS index_stats (
  key TEXT PRIMARY KEY,
  value REAL
);

CREATE TABLE IF NOT EXISTS token_stats (
  token TEXT PRIMARY KEY,
  doc_freq INTEGER DEFAULT 0
);

-- Search Analytics
CREATE TABLE IF NOT EXISTS search_logs (
  id SERIAL PRIMARY KEY,
  query TEXT NOT NULL,
  result_count INTEGER DEFAULT 0,
  search_mode TEXT DEFAULT 'default',
  user_agent TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_logs_created ON search_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs(query);

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
);
CREATE INDEX IF NOT EXISTS idx_search_events_created ON search_events(created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_type_created ON search_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_query_created ON search_events(query_norm, created_at);
CREATE INDEX IF NOT EXISTS idx_search_events_request_id ON search_events(request_id);

-- Indexer Job Queue
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
);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status_available ON index_jobs(status, available_at);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status_lease ON index_jobs(status, lease_until);
CREATE INDEX IF NOT EXISTS idx_index_jobs_created ON index_jobs(created_at);
