# Database Migration Baseline

Closed as an unsubstantiated cleanup proposal on 2026-09-10.

Old table names in migration history are not evidence of a broken current
schema. The fresh-database migration and local search startup were exercised
successfully during the documentation review. This does not certify every
existing production database's upgrade state.

No migration is removed or restamped by this decision. Reopen with a concrete
migration failure, unsupported starting revision, or measured startup cost
before proposing a new baseline. Production schema drift is a separate
verification problem; preserve migration history needed by existing installs.
