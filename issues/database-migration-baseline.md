# Database Migration Baseline

## Problem

The Alembic migration history contains old crawler schema transitions that no
longer match the current intended model.

Older migrations still describe legacy `urls` responsibilities, status-oriented
URL indexes, crawl queue transitions, and intermediate frontier/read-model
states. Keeping that history may make the current schema harder to understand,
especially now that the repository is being simplified around the current
production shape rather than broad backward compatibility.

## Evidence

Examples of stale or potentially misleading migration history:

- legacy `urls.status` and pending-URL indexes
- crawl queue migration steps that predate `frontier_entries`
- intermediate admin read-model migrations that may no longer match the reduced
  admin surface

The current project direction is to keep `urls` as a discovery ledger and keep
crawler runtime/scheduling state out of it. Old migrations can obscure that
target shape.

## Impact

- New readers may infer current design from obsolete migration steps.
- Indexes or columns that are no longer meaningful may look intentionally
  supported.
- Future schema cleanup is harder because it must reason through historical
  states that are no longer operationally important.
- Future schema cleanup is harder to reason about while migration history still
  presents obsolete intermediate states as active design elements.

## Direction

Consider replacing the old migration chain with a current-schema baseline.

Before doing that, verify:

- the production database's current schema
- the production `alembic_version`
- whether deployments run migrations automatically
- whether production can be stamped to a new baseline revision
- whether any other environment still needs to migrate from old revisions

Likely target:

- create a new baseline migration representing the current intended schema
- remove old migration files after confirming no environment depends on them
- stamp the production database to the new baseline if needed
- keep future migrations small and forward-only from that baseline
