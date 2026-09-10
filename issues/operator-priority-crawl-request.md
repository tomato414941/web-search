# Operator Priority Crawl Request

## Current behavior

`web-search-enqueue-url` records URL knowledge and inserts eligible URLs into
`crawl_queue`. It does not fetch synchronously or promise priority. Queue
selection is ordered by creation time and URL hash among host-eligible tasks.
The current schema has no priority bucket or operator-provenance field.

## Decision needed

Determine whether operators need an explicit “crawl this soon” capability beyond
ordinary enqueueing. If so, define:

- how urgency changes ordering without starving normal work;
- which host pacing and admission rules still apply;
- how duplicate, already-running, or failed requests are reported;
- whether an audit trail is required, separately from scheduling priority.

Any implementation should use the normal worker path rather than synchronously
fetching inside an operator HTTP request. This issue incorporates the former
operator-intent and priority-policy issues; it does not require restoring the
old crawler APIs or creating a management UI.
