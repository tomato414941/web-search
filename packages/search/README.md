# Search execution boundary

`SearchEngine` prepares operator-aware queries and returns OpenSearch's native
hybrid ranking as `SearchResult` / `SearchHit`. It has no dependency on the Web
app, PostgreSQL, browser sessions, telemetry, or source-policy configuration.

The host supplies the index, OpenSearch client, and query embedding callable:

```python
from opensearchpy import OpenSearch
from web_search_engine import SearchEngine
from web_search_opensearch.embeddings import get_embeddings

client = OpenSearch(hosts=["http://localhost:9200"])
engine = SearchEngine(
    client,
    get_embeddings().query,
    index="documents-hybrid-v2",
)
result = engine.search("Python", limit=10, page=1)
```

The hybrid index and RRF pipeline must already be provisioned. The callable must
use the same model and vector representation as the document projection.
Retrieval/provider errors propagate; the HTTP host translates them to HTTP 503.
There is no source-aware reranker or alternative search mode.

`packages/opensearch` owns mappings, native queries, and projection embeddings.
`packages/kernel` owns analysis, operators, result types, and snippets.
`apps/frontend` owns runtime wiring, serialization, HTTP, and telemetry. HTML
and JSON use the same adapter; MCP calls the JSON API.

Unit tests inject both external dependencies:

```bash
uv run --package web-search-engine pytest packages/search/tests
```

`make ci-hybrid` additionally verifies real OpenSearch fusion, operator filters,
pagination, ingestion, rebuilds, and public responses with deterministic vectors.
