# Crawl Priority Scheduling Policy

## Problem

The project needs a clear policy for when one crawl target should be prioritized
over another.

Priority scheduling is different from URL registration, operator provenance, and
frontier admission.

## Evidence

The previous crawler `POST /urls` path used `discovered_via="manual"`, which
mapped to the `manual_now` crawl profile and priority bucket. That bundled the
operator request and the priority policy into one implicit behavior.

Current code no longer stores `discovered_via`; operator priority is an
admission-time scheduling intent.

## Impact

- Priority behavior is hard to change without changing URL provenance behavior.
- Operator requests may receive priority because of an implicit convention
  rather than an explicit scheduling decision.

## Direction

Define priority scheduling as its own policy.

Likely target shape:

- crawl priority is derived from explicit scheduling intent
- operator priority requests can exist without synchronous fetch execution
- priority policy can be reviewed independently from URL registry ownership
