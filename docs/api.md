# API Documentation

The `web-search` provides a RESTful JSON API.

**Base URL**: `http://localhost:8080` (default)
**Interactive Docs**: `http://localhost:8080/docs` (Swagger UI)

## Search API

### `GET /api/search`
Perform a search.

**Parameters:**
*   `q` (string, required): The search query.
*   `limit` (int, default=10): Number of results to return.
*   `offset` (int, default=0): Pagination offset.
*   `mode` (string, optional): Search mode (`standard` or `semantic`).

**Response Example:**
```json
{
  "meta": {
    "total": 100,
    "took": 0.05
  },
  "hits": [
    {
      "title": "Example Page",
      "url": "http://example.com",
      "snippet": "This is a matching snippet...",
      "score": 5.2
    }
  ]
}
```

## Crawler API

### `POST /api/crawl`
Submit a URL to the crawler frontier.

**Body:**
```json
{
  "url": "http://target-site.com",
  "priority": 1  // Optional (default: 0)
}
```

### `POST /score/predict`
Predict the crawler priority score for a URL (Internal API).

**Body:**
```json
{
  "url": "http://example.com/login",
  "parent_score": 100.0,
  "visits": 5
}
```

**Response:**
```json
{
  "url": "http://example.com/login",
  "inputs": { ... },
  "predicted_score": 45.0
}
```

## Stats API

### `GET /api/stats`
Get system statistics.

**Response Example:**
```json
{
  "pages_indexed": 1500,
  "queue_size": 200,
  "db_size_mb": 45.2
}
```
