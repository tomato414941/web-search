# API Documentation

The `web-search` project provides a RESTful JSON API across multiple services.

**Global API Prefix**: `/api/v1`

## Services
*   **Frontend Service**: `http://localhost:8083` (Search, Admin, Proxy)
*   **Indexer Service**: `http://localhost:8081` (Write-only)
*   **Crawler Service**: `http://localhost:8082` (Worker Control)

---

## Frontend Service (`:8083`)

### `GET /api/v1/search`
Full-text web search with BM25 ranking and AI-optimized ranking signals.

**Parameters:**
*   `q` (string, required): The search query.
*   `limit` (int, default=10, max=50): Number of results per page.
*   `page` (int, default=1): Page number.
*   `mode` (string, default=`bm25`): Search mode — `bm25`.

**Query operators:**
*   `site:example.com` limits results to a domain.
*   `"exact phrase"` requires an exact phrase match.
*   `-keyword` excludes results containing a term.
*   `-"exact phrase"` excludes results containing an exact phrase.

**Search Modes:**

| Mode | Description |
|---|---|
| `bm25` | Classic keyword matching with BM25 scoring (default) |

**Authentication** (optional):
*   Header: `X-API-Key: pbs_...`
*   Query param: `?api_key=pbs_...`

Anonymous requests are allowed with IP-based rate limiting (100 req/min).
API key users get 1,000 requests/day and usage info in the response.

**Response:**
```json
{
  "query": "python web framework",
  "total": 42,
  "page": 1,
  "per_page": 10,
  "last_page": 5,
  "hits": [
    {
      "url": "https://example.com/fastapi",
      "title": "FastAPI - Modern Python Web Framework",
      "snip": "A modern, fast web framework for building APIs with <mark>Python</mark>...",
      "snip_plain": "A modern, fast web framework for building APIs with Python...",
      "rank": 12.5,
      "indexed_at": "2026-03-01T12:00:00.000000+00:00",
      "published_at": "2026-02-28T09:30:00+00:00",
      "temporal_anchor": 1.0,
      "authorship_clarity": 0.8,
      "factual_density": 0.72,
      "origin_score": 0.85,
      "origin_type": "spring",
      "author": "Sebastián Ramírez",
      "organization": "FastAPI"
    }
  ],
  "mode": "bm25",
  "request_id": "a1b2c3d4e5f6"
}
```

**Hit fields** (all optional, omitted when null):

| Field | Description |
|---|---|
| `temporal_anchor` | Temporal transparency score (0.0-1.0). 1.0 = `published_at` present |
| `authorship_clarity` | Author/org metadata presence (0.0-1.0) |
| `factual_density` | Verifiable facts per unit of text (0.0-1.0) |
| `origin_score` | Information origin score (0.0-1.0). Higher = closer to primary source |
| `origin_type` | `spring` / `river` / `delta` / `swamp` |
| `author` | Author name from HTML metadata |
| `organization` | Publisher/organization from HTML metadata |

With a valid API key, the response also includes:
```json
{
  "usage": { "daily_used": 5, "daily_limit": 1000 }
}
```

### `POST /api/v1/search/click`
Log a click event for relevance feedback.

**Body:**
```json
{
  "request_id": "a1b2c3d4e5f6",
  "query": "python",
  "url": "https://example.com",
  "rank": 1
}
```

**Response:** `204 No Content`

### `POST /api/v1/crawl`
Manually submit a URL to the crawler (proxies to Crawler Service).

**Body:**
```json
{
  "url": "http://target-site.com"
}
```

### `GET /api/v1/stats`
Get system statistics (queue size, indexed count).

### `GET /api/v1/quality/summary`
Search quality metrics summary.

### `GET /health`
Health check. Returns `{"status": "ok"}`.

### `GET /readyz`
Readiness check. Returns status of database, crawler, OpenSearch, and embeddings.

### Admin Endpoints (session auth required)

| Endpoint | Description |
|---|---|
| `GET /admin/` | Dashboard |
| `GET /admin/login` | Login page |
| `POST /admin/login` | Authenticate |
| `GET /admin/logout` | Logout |
| `GET /admin/seeds` | Seed URL management |
| `POST /admin/seeds` | Add seed URLs |
| `POST /admin/seeds/delete` | Remove seeds |
| `POST /admin/seeds/import-tranco` | Import from Tranco list |
| `GET /admin/queue` | View crawl queue |
| `POST /admin/queue` | Enqueue URLs |
| `GET /admin/history` | Crawl history |
| `GET /admin/crawlers` | Crawler workers status |
| `POST /admin/crawler/start` | Start crawler |
| `POST /admin/crawler/stop` | Stop crawler |
| `GET /admin/indexer` | Indexer status and jobs |
| `POST /admin/indexer/retry-job` | Retry a failed job |
| `GET /admin/analytics` | Search analytics |
| `GET /admin/api-keys` | API key management |
| `POST /admin/api-keys` | Create API key |
| `DELETE /admin/api-keys/{key_id}` | Delete API key |

---

## Indexer Service (`:8081`)

### `POST /api/v1/indexer/page`
Queue a crawled page for asynchronous indexing.

**Headers:**
*   `X-API-Key`: (Required)

**Body:**
```json
{
  "url": "http://example.com",
  "title": "Page Title",
  "content": "Full page text content...",
  "outlinks": ["http://example.com/about"],
  "published_at": "2026-01-15T10:00:00Z",
  "author": "John Doe",
  "organization": "Example Inc"
}
```

**Response (`202 Accepted`):**
```json
{
  "ok": true,
  "queued": true,
  "job_id": "uuid",
  "deduplicated": false,
  "url": "http://example.com/"
}
```

### `GET /api/v1/indexer/jobs/{job_id}`
Get asynchronous indexing job status.

### `GET /api/v1/indexer/jobs/failed`
List failed indexing jobs.

### `POST /api/v1/indexer/jobs/{job_id}/retry`
Retry a failed job.

### `POST /api/v1/indexer/pagerank`
Trigger PageRank calculation.

### `POST /api/v1/indexer/origin-scores`
Recalculate information origin scores from the link graph. Classifies documents as spring/river/delta/swamp based on in-link/out-link ratio.

### `GET /api/v1/indexer/stats`
Indexer statistics: page count and job queue metrics. Requires `X-API-Key` header.

### `GET /health`
Health check.

---

## Crawler Service (`:8082`)

### `POST /api/v1/urls`
Directly enqueue URLs into the frontier.

### `GET /api/v1/queue/status`
Queue statistics (pending, crawling, done, failed counts).

### `GET /api/v1/queue/queue`
Inspect the frontier queue (peek at pending URLs).

### Worker Control

| Endpoint | Description |
|---|---|
| `POST /api/v1/worker/start` | Start crawler worker |
| `POST /api/v1/worker/stop` | Stop crawler worker |
| `GET /api/v1/worker/status` | Worker status (running, uptime) |

### Seeds

| Endpoint | Description |
|---|---|
| `GET /api/v1/seeds` | List seed URLs |
| `POST /api/v1/seeds` | Add seeds |
| `DELETE /api/v1/seeds` | Remove seeds |
| `POST /api/v1/seeds/import-tranco` | Import from Tranco ranking |

### Statistics

| Endpoint | Description |
|---|---|
| `GET /api/v1/stats` | Aggregated crawler stats |
| `GET /api/v1/stats/frontier` | Frontier stats (domains, stale URLs) |
| `GET /api/v1/stats/breakdown` | Status breakdown |

### `GET /api/v1/history`
Recent crawl history.
