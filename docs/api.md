# API Documentation

The `web-search` project provides a RESTful JSON API across multiple services.

**Global API Prefix**: `/api/v1`

## Services
*   **Frontend Service**: `http://localhost:8080` (Search, Admin, Proxy)
*   **Indexer Service**: `http://localhost:8081` (Write-only)
*   **Crawler Service**: `http://localhost:8000` (Worker Control)

---

## Frontend Service (`:8080`)

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

---

## Indexer Service (`:8081`)

### `POST /api/v1/indexer/page`
Submit a crawled page for indexing.

**Headers:**
*   `X-API-Key`: (Required)

**Body:**
```json
{
  "url": "http://example.com",
  "title": "Page Title",
  "content": "Full page text content...",
  "raw_html": "<html>...</html>" // Optional
}
```

### `GET /api/v1/health`
Health check and index stats.

---

## Crawler Service (`:8000`)

### `POST /api/v1/urls`
Directly enqueue URLs.

### `GET /api/v1/queue`
Inspect the frontier queue.
