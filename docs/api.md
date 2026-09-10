# API behavior

The frontend provides search and stored-content access without an API key.
Its `/docs` and `/openapi.json` describe request and response fields. This
document covers behavior that clients must account for beyond those schemas.

## Search

`GET /search-results?q=...` searches the existing index; it does not crawl on
demand. BM25 is the only implemented retrieval mode.

| Input | Current handling |
|---|---|
| `q` | Trimmed, then truncated to 200 characters by default. Missing or empty input returns no hits. |
| `limit` | Defaults to 10; invalid integers use that default. Values are clamped to 1–50 by default. |
| `page` | Defaults to 1; invalid integers use that default. Values are clamped to 1–100 by default. |
| `mode` | Currently ignored; execution and `requested_mode` are always `bm25`. |
| `include_content` | Enabled only by the literal string `true`. |

Queries support `site:`, quoted phrases, and excluded terms or phrases. A query
needs positive searchable text: a site filter or exclusions alone do not list
all matching documents. Phrase matching operates on analyzed tokens.

`snip` contains highlight markup; use `snip_plain` when plain text is needed.
`score` is the OpenSearch score, not a final score for the Python reranking
policy. Returned order can therefore differ from descending `score`.

`include_content=true` returns the OpenSearch copy of the extracted text,
currently limited to the first 20,000 characters. It does not return the full
stored document. Use the content endpoint below for that.

### Failures and interpretation

- Retrieval failures currently return HTTP 200 with `degraded: true`,
  `error_type: "retrieval_failed"`, zero total, and an empty hit list.
  Do not count this response as a successful zero-result search.
- OpenSearch being disabled also produces this degraded response for a
  non-empty searchable request; there is no alternative retrieval backend.
- Search is rate-limited to 100 requests per minute per IP. Exceeding the limit
  returns HTTP 429.
- A `request_id` may be returned when request telemetry is saved. The JSON API
  does not create browser sessions or result impressions. The HTML search page
  separately records impressions and accepts click events.

See `search-ranking-policy.md` for candidate selection and pagination limits.

## Stored content and index count

`GET /indexed-documents/by-url?url=...` reads the full extracted text from
PostgreSQL, without fetching the live page. Unknown URLs return HTTP 404. The
endpoint has the same 100 requests/minute/IP limit as search.

`indexed_at` is the document's indexing timestamp, not its publication date or
proof that the source is still current. PostgreSQL can contain documents that
are absent from the search projection.

`GET /indexed-documents` returns `{"documents": {"total": N}}`, the OpenSearch
document count. This is not a count of every known URL or completed crawl.

## Health checks

`GET /health` is liveness only. `GET /readyz` returns HTTP 200 or 503 according
to database availability in each service.

The frontend additionally reports crawler connectivity and OpenSearch status,
but neither affects its readiness status code. A successful readiness response
does not prove that search works. After a deployment, inspect these dependency
statuses and run a search. Frontend health routes are omitted from OpenAPI.

## Private ingestion API

`POST /documents` on the indexer accepts `url`, `title`, and `content` and
requires the configured key in `X-API-Key`. It performs the PostgreSQL write
within the request, then attempts OpenSearch indexing when enabled. It is not
an asynchronous job-submission API.

The current single-document path logs OpenSearch failures without failing the
request. Consequently, HTTP 200 and `indexed: true` confirm the completed
document write, but do not guarantee search visibility. Check the projection
when diagnosing missing results. The crawler treats HTTP 200 as a successful
handoff.
