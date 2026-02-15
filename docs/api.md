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
Perform a search.

**Parameters:**
*   `q` (string, required): The search query.
*   `limit` (int, default=10): Number of results.
*   `page` (int, default=1): Page number.
*   `mode` (string, optional): `default` (BM25), `semantic` (Vector), or `hybrid`.

**Response:**
```json
{
  "query": "test",
  "total": 100,
  "page": 1,
  "hits": [
    {
      "url": "http://example.com",
      "title": "Example Page",
      "snip": "This is a matching snippet...",
      "rank": 0.95
    }
  ]
}
```

### `POST /api/v1/crawl`
Manually submit a URL to the crawler (Proxies to Crawler Service).

**Body:**
```json
{
  "url": "http://target-site.com"
}
```

### `GET /api/v1/stats`
Get system statistics (Queue size, Indexed count).

### `POST /admin/crawler/start`
Start the crawler worker (Admin only).

### `POST /admin/crawler/stop`
Stop the crawler worker (Admin only).

### `GET /admin/analytics`
View Search Analytics (Admin only).

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
  "outlinks": ["http://example.com/about"]
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

### `GET /health` (recommended) or `GET /api/v1/health`
Health check. Root-level `/health` is preferred; `/api/v1/health` is for backward compatibility.

---

## Crawler Service (`:8082`)

### `POST /api/v1/urls`
Directly enqueue URLs.

### `GET /api/v1/queue`
Inspect the frontier queue.
