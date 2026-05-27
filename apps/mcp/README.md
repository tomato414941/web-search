# PaleBlueSearch MCP Server

MCP server for [PaleBlueSearch](https://palebluesearch.com) — search the web with freshness metadata that AI agents can trust.

## Tools

### `web_search`

Search the web and get results with publication and indexing timestamps.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | (required) | Search query |
| `limit` | int | 10 | Results per page (1-50) |
| `mode` | string | "bm25" | `bm25` |
| `page` | int | 1 | Page number |

### `get_stats`

Get index statistics (indexed pages, frontier depth, URLs visited).

## Setup

### Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "paleblue-search": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/web-search",
        "--package",
        "paleblue-search-mcp",
        "python",
        "-m",
        "paleblue_mcp"
      ]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "paleblue-search": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/web-search",
        "--package",
        "paleblue-search-mcp",
        "python",
        "-m",
        "paleblue_mcp"
      ]
    }
  }
}
```

### Install Dependencies

```bash
make sync-mcp
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PALEBLUE_BASE_URL` | `https://palebluesearch.com` | API base URL |
| `PALEBLUE_TIMEOUT` | `30` | HTTP timeout in seconds |

## Why Freshness Metadata?

Every search result includes `indexed_at` and `published_at` timestamps. AI agents can use these to:

- Filter out stale information
- Prioritize recent sources
- Cite when information was published and last verified

## License

MIT
