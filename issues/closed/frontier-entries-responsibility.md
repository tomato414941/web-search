# Frontier Entries Responsibility

Superseded by the queue implementation; closed on 2026-09-10.

The issue described durable per-URL schedules and leases in `frontier_entries`.
The current runtime instead uses `crawl_queue`, created by migration 017; the
old `crawl_schedule` was dropped by migration 019. Queue rows are removed when
popped, and attempt completion updates host state and logs.

The old rename/split options do not describe work still pending on an existing
schedule table. The resulting delivery and recovery question is recorded in
`issues/crawl-queue-delivery-semantics.md`.
