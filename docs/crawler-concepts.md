# Crawler queue and handoff

These boundaries separate knowledge of URLs, decisions to fetch them, and the
outcome of a fetch. They matter when changing admission, retries, or operator
commands.

## Current state model

| State | Meaning |
|---|---|
| `urls` | URLs known to the Web model; registration alone does not schedule work |
| `links` | Observed references, including targets not yet crawled or indexed |
| `crawl_queue` | Pending tasks, removed when selected for processing |
| `domain_state` | Host pacing and backoff, separate from per-URL queue entries |

`pop_ready_crawl_tasks()` selects rows with transaction locks and removes them
before returning work to the process. The worker tracks active tasks in memory.
There is no persistent per-URL lease, automatic lease-expiry recovery, or
retained per-URL recrawl schedule in this implementation.

A process crash or cancellation after a pop can lose that attempt from the queue.
Ordinary failure handling logs the attempt and updates domain state; it does
not reinsert the task. Rediscovery, operator enqueue, or frontier refill may
introduce the URL again. Do not assume at-least-once delivery from this queue.

## Admission

URL registration, admission, and prioritization are different operations.
The current paths are:

- HTML discovery records valid known URLs but selects at most one eligible
  same-domain outlink for enqueueing. Query strings, fragments, and wildcard
  paths are filtered from ordinary HTML queue candidates.
- Discovered syndication feeds use their own admission path. Feed entry URLs
  are recorded as knowledge without automatic enqueueing.
- The operator enqueue CLI records URL knowledge and requests normal queue
  insertion; it does not synchronously fetch or promise priority.
- Frontier refill samples observed links, selects diverse unindexed and
  unqueued targets, records them, and requests queue insertion.

The queue applies URL admission rules and deduplicates pending rows by URL hash.
Selection considers host pacing/backoff and queue age. A URL that has already
been popped is no longer protected by that pending-row deduplication.

## Handoff semantics

The per-target path performs crawl checks, fetches the resource, extracts text
and references, submits HTML content to the indexer, and records the outcome.

The crawler posts to `/documents` and treats HTTP 200 as success. Its submission
timeout is currently three seconds by default. The indexer performs its document
write within the request; there is no asynchronous indexer job queue.

A successful handoff does not establish OpenSearch visibility. The indexer can
log a projection failure and still return HTTP 200. A client timeout can also
leave the caller uncertain whether a write completed. Diagnose submission,
stored-document state, and search projection separately.

## Why keep the per-target work bounded

Global summaries and graph-rank maintenance should not extend every page's
fetch path. `issues/closed/frontier-stats-heavy-aggregation.md` records how
repeated full-frontier aggregates caused database load in an earlier design.
That historical evidence explains the boundary; its old table and admin-page
names do not describe the current runtime.

Remaining admission and priority questions live in `issues/`. A durable retry or
recrawl model would be a new design decision, not an existing queue guarantee.
