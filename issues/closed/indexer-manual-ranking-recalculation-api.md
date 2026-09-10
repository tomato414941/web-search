# Ranking Recalculation Execution Boundary

Closed after implementation review on 2026-09-10.

The indexer exposes ingestion, health, and metrics; it has no ranking-maintenance
HTTP endpoint. Scheduled PageRank and domain-rank calculation belong to the Web
model maintenance worker, and explicit reruns use its CLI.

This resolves the original execution-boundary concern. An operation/job UI is
not an established requirement. Rank freshness, projection refresh, memory
cost, and quality verification remain in `issues/link-authority-signal-design.md`.
