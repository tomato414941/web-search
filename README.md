# PaleBlueSearch

PaleBlueSearch is a Web search project with its own crawler, extracted-document
store, OpenSearch retrieval, browser UI, JSON API, and MCP adapter.

The goal is general-purpose Web search. Retrieval combines Japanese-tokenized
BM25 and dense vectors using OpenSearch’s native reciprocal rank fusion (RRF).
Search quality and corpus coverage remain work in progress.

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
OpenSearch is a required service. Set `OPENAI_API_KEY` for document and query
embeddings. A plain `docker compose up` does not publish the frontend port.

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
