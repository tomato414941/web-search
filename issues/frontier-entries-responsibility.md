# Frontier Entries Responsibility

## Problem

`frontier_entries` is not a pure queue, but its name and surrounding language make
it easy to treat it as one.

In the current implementation, a row usually remains after a crawl attempt. The
row is updated with execution state such as `status`, `next_fetch_at`,
`last_fetched_at`, `last_success_at`, `fail_streak`, and lease fields. That makes
the table closer to a durable crawl target/schedule table than a disposable
work queue.

## Evidence

Current responsibilities mixed into `frontier_entries`:

- crawl target identity for URLs that should be fetched repeatedly
- scheduling state such as `next_fetch_at`, priority, and crawl profile
- worker execution state such as `pending`, `leased`, lease token, and lease
  expiry
- crawl result state such as last fetch/success timestamps and failure streak

This ambiguity matters because `urls` is intended to stay a simple discovery
ledger. Moving execution state back into `urls` would make the largest URL table
heavier, but keeping it in `frontier_entries` without a clear definition makes
the runtime model harder to reason about.

## Impact

- RSS/feed URLs feel awkward in `frontier_entries` if the table is understood as
  a page crawl queue.
- `urls.last_crawled_at` and `urls.crawl_count` duplicate or overlap with crawl
  execution state already stored in `frontier_entries`.
- Future changes may keep adding queue, schedule, lease, and admin-read concerns
  to the same table because the boundary is unclear.

## Direction

Decide what `frontier_entries` is the source of truth for.

Likely options:

- define it explicitly as durable crawl target/schedule state and stop calling it
  a queue
- rename it later to something like `crawl_schedules` or `crawl_targets`
- split durable schedule state from transient worker lease state if operational
  complexity justifies it

Do not move crawl execution state back into `urls` unless there is a stronger
reason than reducing table count. `urls` should remain a simple, large discovery
ledger.
