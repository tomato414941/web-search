# Operator URL Intent Boundary

## Problem

The project needs a clear way to represent that a URL came from an operator
request.

Operator intent is provenance and intent. It is not itself URL registration,
frontier admission, or priority scheduling.

## Evidence

The previous crawler `POST /urls` path encoded operator intent by passing
`discovered_via="manual"`, which also caused manual priority behavior.

That made operator provenance and scheduling policy hard to separate.

Current frontier admission no longer stores `discovered_via`. Operator priority
is represented as scheduling intent at admission time, not as URL provenance.

## Impact

- Operator provenance can accidentally imply priority behavior if it is stored
  as a URL category.
- The system cannot clearly distinguish "an operator supplied this URL" from
  "this URL must be crawled before ordinary crawler-discovered URLs."
- Future operator controls may reuse crawler-specific internals instead of a
  clear intent model.

## Direction

Define operator URL intent separately from scheduling.

Likely target shape:

- operator-submitted URLs carry explicit provenance
- priority behavior is applied by a scheduling policy, not by provenance alone
- operator actions should be auditable without requiring a synchronous crawl API
