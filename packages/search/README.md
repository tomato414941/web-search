# Search execution boundary

`web_search_engine.SearchEngine` owns query preparation, candidate retrieval,
and ranking. It returns `SearchResult` / `SearchHit` objects from
`web_search_kernel`. It depends on the analyzer, OpenSearch adapter, and search
policy data, and has no dependency on the Web app, PostgreSQL, cookies, HTML,
FastAPI, or Prometheus.

The caller supplies an OpenSearch client and the index to search:

```python
from opensearchpy import OpenSearch
from web_search_engine import SearchEngine

client = OpenSearch(hosts=["http://localhost:9200"])
engine = SearchEngine(client, index="evaluation-documents")
result = engine.search("GitHub", limit=10, page=1)
```

The index must already exist. The current source-aware policy still uses
`config/canonical_sources.json`, resolved by `web_search_search_config`.
Run from the repository root, or provide that config directory in the working
directory of an installed application. This refactor does not change the
ranking policy or its weights.

## Ownership

| Layer | Responsibilities |
|---|---|
| `packages/search` | Query preparation, retrieval planning, source policy, reranking, typed results; retrieval exceptions propagate |
| `packages/kernel` | Shared analyzer, query operators, result types, snippet helpers |
| `packages/opensearch` | OpenSearch requests, mappings, client utilities |
| `apps/frontend/services/search.py` | Runtime client setup, metrics, degraded-response behavior, response serialization |
| HTML and JSON routes | Input limits, HTTP responses, presentation, request telemetry |
| HTML route and click endpoint | Browser sessions, displayed-result impressions, click tracking |

The Web UI and public API use the same Web adapter. MCP uses the public API.
The JSON API records requests but does not create browser sessions or result
impressions. Neither presentation format is part of the engine contract.

`apps/frontend` remains the HTTP host for search and stored-content APIs. Its
database access for content and telemetry, and its operational dependency
checks, remain host concerns. There is no new service or network hop.

## Verification

```bash
uv run --package web-search-engine pytest packages/search/tests
```

These tests use a supplied fake OpenSearch client and need no Web server,
PostgreSQL, indexer credentials, or live OpenSearch. They cover the existing
ranking behavior and guard against importing Web runtime dependencies into the
engine. The Web tests separately cover response formatting, failure handling,
and the difference between API request logging and browser click tracking.
