# PaleBlueSearch MCP adapter

This adapter calls the public search/content API and exposes two MCP tools.
It reads already indexed pages; it does not browse or crawl a URL on demand.

## Connect a client

Install workspace dependencies from the repository root:

```bash
make sync-mcp
```

Use this server entry in a client's MCP configuration, replacing the repository
path. For clients using `mcpServers` JSON, such as Claude Code's `.mcp.json`, the
configuration is:

```json
{
  "mcpServers": {
    "paleblue-search": {
      "command": "uv",
      "args": [
        "run", "--directory", "/path/to/web-search",
        "--package", "paleblue-search-mcp", "python", "-m", "paleblue_mcp"
      ]
    }
  }
}
```

The client must be able to start `uv` and read that checkout. The server uses
stdio; its logs go to stderr.

## Tools and limitations

| Tool | Use |
|---|---|
| `web_search(query, limit=10, mode="bm25", page=1, include_content=false)` | Search and return Markdown results. Limit is clamped to 1–50; BM25 is the only serving mode. |
| `fetch_content(url)` | Read the full extracted text of an indexed URL from the document store, without re-fetching the live page. |

`include_content=true` returns the bounded search projection, currently at most
20,000 characters per page. For complete stored text, call `fetch_content`.
The latter can display `indexed_at`; this is an indexing time, not a publication
date or assurance that the page is up to date.

The adapter currently formats a degraded API search with no hits as “No results
found.” It does not expose the API's `degraded` flag in that text. Diagnose an
unexpected empty search through the JSON API before treating it as a coverage
failure. Transport errors are returned as tool text beginning with `Search
failed:` or `Content fetch failed:`.

Search behavior and HTTP failure semantics are in `docs/api.md` at the
repository root.

## Environment

| Variable | Default |
|---|---|
| `PALEBLUE_BASE_URL` | `https://palebluesearch.com` |
| `PALEBLUE_TIMEOUT` | `30` seconds |

For a local frontend, pass `PALEBLUE_BASE_URL=http://localhost:8083` in the MCP
server process environment.
