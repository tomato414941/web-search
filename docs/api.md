# API behavior

The frontend provides public search and stored-content access. `/docs` and
`/openapi.json` describe its request and response schemas.

## Search

`GET /search-results?q=...` searches the existing hybrid index; it does not crawl
on demand. The response identifies its retrieval mode as `hybrid`.

| Input | Handling |
|---|---|
| `q` | At most 200 characters, then trimmed. Missing/empty input returns no hits. |
| `limit` | Integer 1–50; default 10. |
| `page` | Positive integer; default 1. Must start within the first 200 results. |
| `include_content` | Boolean; default false. |

Invalid or unknown parameters return HTTP 422. There is no search-mode input.
Queries support `site:`, quoted phrases, and excluded terms/phrases. Operators
constrain both lexical and vector results. Positive searchable text is required.

`total` counts accessible results up to the 200-result window; `last_page` uses
that bounded total. `score` is the native RRF score, and returned order is not
subsequently overridden. See `search-ranking-policy.md` for the query semantics.

`snip` contains highlight markup; `snip_plain` is plain text.
`include_content=true` includes at most the first 20,000 content characters from
OpenSearch. Fetch full stored text using the content endpoint below.

Embedding/retrieval failures return HTTP 503, not an empty successful result.
There is no BM25 fallback. Rate limiting returns HTTP 429 after 100 requests per
minute per IP. An optional `request_id` identifies saved telemetry; JSON search
does not create browser sessions or result impressions. HTML separately records
impressions and accepts click events.

## Stored content and count

`GET /indexed-documents/by-url?url=...` reads full extracted text from PostgreSQL
without fetching the live page. Unknown URLs return HTTP 404. The rate limit is
100 requests/minute/IP. `indexed_at` is the storage timestamp, not publication
time or a freshness guarantee. Stored documents can be excluded from search.

`GET /indexed-documents` returns `{"documents": {"total": N}}`, the OpenSearch
index count. It does not count all known URLs or completed crawls.

## Health

`/health` reports process liveness. Frontend `/readyz` requires PostgreSQL, the
hybrid index schema, the search pipeline, and a configured embedding API key.
It does not make a paid provider request or certify model access/quota. Verify
an actual search after deployment. Indexer readiness currently checks its DB.

## Private ingestion

Indexer `POST /documents` accepts `url`, `title`, and `content`, authenticated by
`X-API-Key`. It stores text in PostgreSQL and generates/project vectors into
OpenSearch within the request. Projection failures fail the request; the DB
write can already have committed. The two stores are not an atomic transaction.
Excluded or empty pages are stored but removed from the search projection.
HTTP success does not bypass OpenSearch's normal refresh delay.
