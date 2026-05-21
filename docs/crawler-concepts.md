# Crawler Concepts

## Status

Current conceptual reference.

This document defines the core concepts used to reason about the crawler in
PaleBlueSearch. It sits above current runtime details and above short-term
implementation plans.

## Core View

The crawler exists to turn reachable web resources into indexable pages and new
crawl candidates.

Its value is not in owning every downstream concern. Its value is in moving
pages through a small, reliable ingestion path while preserving enough safety
and scheduling discipline to keep the system operable.

## Core Concepts

### Frontier

The `frontier` is the durable set of crawlable targets that may be worked in
the future.

The frontier is not just a queue. It is the crawler-side representation of what
may be crawled, when it may be crawled, and what is currently leased.

### Lease

A `lease` is a temporary claim on one frontier target by one worker slot.

Leasing exists to support parallelism without losing durable coordination.
Workers should do bounded work under a lease and then either complete or give
the work back through explicit frontier state transitions.

### Domain Scheduling

`Domain scheduling` is the part of crawler state that limits how aggressively a
single host is visited.

It is separate from the frontier itself. The frontier answers "what may be
crawled"; domain scheduling answers "what may be crawled now from this host."

### Hot Path

The `hot path` is the per-target work that occupies a worker slot.

Conceptually, the crawler hot path is:

`lease -> safety check -> fetch -> parse -> enqueue -> frontier update`

This path should stay small, bounded, and easy to reason about.

### Side Path

A `side path` is useful crawler-adjacent work that should not dominate the hot
path.

Examples include operator summaries, rollups, maintenance jobs, and other
derived views of crawler state.

### Safety

`Safety` means the narrow set of checks required to avoid obviously harmful or
invalid crawling behavior.

Safety is part of the crawler, but it should remain explicit and bounded. It
should not become a place where every policy, reporting concern, or downstream
dependency accumulates.

### Operator Read Model

An `operator read model` is a derived view of crawler state meant for humans,
not the runtime source of truth itself.

Operator views may summarize, cache, or reshape crawler state. They should not
be confused with the durable scheduling state that workers depend on.

### Downstream Boundary

The `downstream boundary` is the handoff from crawler work to indexer work.

The crawler is successful when a parsed page has been accepted at that
boundary. Search indexing completion, ranking updates, and enrichments are
downstream concerns.

## Responsibility Boundaries

The crawler should own:

- frontier leasing and frontier state transitions
- domain pacing and host-level scheduling discipline
- lightweight safety checks
- HTTP fetching
- content extraction
- outlink discovery
- handoff to the indexer
- persistence of crawl outcomes

The crawler should not own:

- search ranking completion
- embedding or later enrichment completion
- heavy operator summary recomputation
- broad downstream retry orchestration

## Conceptual Splits

The crawler becomes easier to reason about when these concerns stay separate:

- durable crawl state vs operator-facing summaries
- queue truth vs host pacing truth
- runtime safety checks vs product policy
- hot-path work vs maintenance work
- crawler completion vs downstream completion

## Implications For This Repository

This repository should prefer:

- a small crawler hot path
- durable state with explicit roles
- side-path operator views instead of hot-path summary work
- fail-fast downstream handoff boundaries
- crawler logic that can change without redefining the whole scheduling model

This implies a preference for:

- bounded in-slot work instead of long retry loops
- requeue and reschedule over stubborn per-slot retry
- narrow safety checks over broad implicit policy coupling
- explicit read models over recomputing large summaries in request or crawl
  paths

## Relationship To Other Documents

- [architecture.md](./architecture.md): current crawler runtime and state layout
- [../issues/](../issues/): current crawler implementation issues
- [deployment.md](./deployment.md): deployment and operations flow

This document defines the conceptual layer used to discuss those documents
consistently.
