"""
SQLite Database Module (Shared Kernel)

Schema definitions and database operations for the search index.
Used by both Frontend (Read) and Indexer (Write) services.
"""

import sqlite3
from shared.core.infrastructure_config import settings

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
  url UNINDEXED,
  title,
  content,
  raw_title UNINDEXED,
  raw_content UNINDEXED,
  tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS links (
  src TEXT,
  dst TEXT
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);

CREATE TABLE IF NOT EXISTS page_ranks (
  url TEXT PRIMARY KEY,
  score REAL
);

CREATE TABLE IF NOT EXISTS page_embeddings (
  url TEXT PRIMARY KEY,
  embedding BLOB
);
"""


def open_db(path: str = settings.DB_PATH) -> sqlite3.Connection:
    """Open database connection and ensure schema exists."""
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    return con


def ensure_db(path: str = settings.DB_PATH) -> None:
    """Ensure database file exists with correct schema."""
    con = open_db(path)
    con.close()


def upsert_page(
    con: sqlite3.Connection,
    url: str,
    title: str,
    content: str,
    raw_title: str | None = None,
    raw_content: str | None = None,
) -> None:
    """Insert or update a page in the index."""
    # For simplicity, delete -> insert for same URL
    con.execute("DELETE FROM pages WHERE url = ?", (url,))
    con.execute(
        "INSERT INTO pages(url,title,content,raw_title,raw_content) VALUES(?,?,?,?,?)",
        (url, title, content, raw_title or title, raw_content or content),
    )
