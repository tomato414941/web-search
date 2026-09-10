# PaleBlueSearch

PaleBlueSearch is a Web search project with its own crawler, extracted-document
store, OpenSearch retrieval, browser UI, JSON API, and MCP adapter.

The goal is general-purpose Web search. The current baseline is BM25 with
Japanese tokenization and source-aware reranking; search quality and corpus
coverage remain work in progress. Vector retrieval is not in the serving path.

## Try the API

```bash
curl --get 'https://palebluesearch.com/search-results' \
  --data-urlencode 'q=python web framework'
```

Results contain URLs, titles, snippets, and scores. Search does not fetch pages
on demand. Use `/indexed-documents/by-url` for full stored text after searching.
See `docs/api.md` for failure behavior, content limits, and readiness semantics.

## Run locally

Follow `docs/setup.md` for a working local search stack and sample data.
A plain `docker compose up` does not publish the frontend port and does not
start OpenSearch by default. Search needs both the `search` profile and
`OPENSEARCH_ENABLED=true`.

For Python development:

```bash
make sync
make ci
```

`apps/` contains service entry points and the MCP adapter; `packages/` contains
shared libraries. The search execution boundary is implemented in
`packages/search`. Current ownership and consistency constraints are described
in `docs/architecture.md`.

## License

MIT
