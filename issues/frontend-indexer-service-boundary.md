# Frontend and Indexer Service Boundary

Observation issue; no service merge is decided.

The frontend serves public search/content and browser UI, and records telemetry.
The indexer accepts authenticated document writes and projects them to
OpenSearch. Both share PostgreSQL. There is no admin UI, MCP stats surface, or
indexer job queue in the current runtime.

Search execution has been separated from the HTTP host into `packages/search`.
That code boundary addresses independent retrieval/ranking work; it does not
answer whether two deployed services remain worthwhile.

Revisit service separation if there is evidence of recurring coordinated
changes, configuration failures, or deployment/debugging cost that outweighs the
public/private boundary. Record the observed cost before proposing a merge.
The presence of two service directories alone is not sufficient evidence.
