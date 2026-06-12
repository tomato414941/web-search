# Links Physical Schema Drift

## Problem

The `links` table physical schema can drift from the migration-defined schema in
long-lived databases.

The current migration baseline defines `links` as a deduplicated URL edge table:

- `PRIMARY KEY (src, dst)`
- `idx_links_src`
- `idx_links_dst`

Fresh local databases match that shape. An existing deployed database does not:
it has no `links` constraint and only `idx_links_src`.

## Evidence

Migration baseline:

- `db/alembic/versions/001_initial_schema.py` creates `links`
- `src` and `dst` are `TEXT NOT NULL`
- `PRIMARY KEY (src, dst)` is expected
- indexes on both `src` and `dst` are expected

Fresh local schema after migrations:

- constraint: `links_pkey PRIMARY KEY (src, dst)`
- indexes: `links_pkey`, `idx_links_src`, `idx_links_dst`

Observed deployed schema:

- no constraints on `links`
- only `idx_links_src`
- table is already large

Full duplicate detection was intentionally not run during this investigation
because `GROUP BY src, dst` across the full table can be expensive on a large
link graph.

## Impact

- `ON CONFLICT DO NOTHING` on `links` does not provide the intended deduplication
  guarantee without a unique constraint.
- Duplicate `(src, dst)` rows may already exist and would block adding
  `PRIMARY KEY (src, dst)` until cleaned.
- Missing `idx_links_dst` makes inbound-link and destination-oriented queries
  more expensive.
- PageRank and domain-rank computations are more fragile because they read from
  a graph table whose physical invariants are not guaranteed.

## Direction

Do not repair this blindly.

Plan a safe, explicit repair path:

- confirm whether duplicate `(src, dst)` rows exist using a bounded or staged
  approach
- define a deduplication strategy if duplicates exist
- create the missing destination index without blocking normal operation
- add the unique constraint or primary key only after duplicates are resolved
- verify that `web-model` writes continue to work after the constraint is in
  place

This should be handled separately from the `web-model` ownership move and
separately from rank-computation design.

## Open Questions

- Should `links` use a primary key, a unique index, or another edge identity?
- Should duplicate cleanup preserve the earliest row, latest row, or simply one
  arbitrary row?
- Should `links` remain untyped, or should future relation type affect the
  uniqueness key?
- Can the repair be done online for the current table size?

## Resolution (2026-06-12)

Repaired on the production database via a one-shot rebuild
(`scripts/migrations/repair_links_schema_drift.sh`, removed after execution):

- duplicates confirmed: 161.9M rows reduced to 136.9M distinct rows (~15.4%
  excess removed)
- rebuilt `links` with `NOT NULL`, `PRIMARY KEY (src, dst)`, `idx_links_src`,
  and `idx_links_dst`, matching the migration baseline
- `ON CONFLICT DO NOTHING` now has a real uniqueness guarantee; crawler
  delete-then-insert writes verified after the swap
- the Hetzner volume holding PostgreSQL data was resized 100GB -> 130GB to fit
  the primary key build (index footprint: 21GB table + 27GB indexes)

Answers to the open questions: duplicate rows were fully identical, so no
keep-earliest/latest policy was needed. The rebuild ran online except for the
crawler, which was stopped during the operation.

Follow-up observation recorded during the repair: `RankingRepository
.fetch_links()` materializes the full edge list in memory, which cannot work at
the current graph size (137M edges vs 8GB host RAM). This belongs to
`issues/link-authority-signal-design.md`.

## Related

- `issues/web-model-boundary.md`
- `issues/closed/link-rank-computation-boundary.md`
