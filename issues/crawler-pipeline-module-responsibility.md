# Crawler Pipeline Module Responsibility

## Problem

`apps/crawler/src/web_search_crawler/workers/pipeline.py` carries more
responsibility than its path suggests.

The file lives under `workers/`, but it contains core crawl-processing logic:
fetch result handling, HTML parsing orchestration, feed parsing orchestration,
indexer submission, discovered-link admission, and crawl result recording.

## Evidence

Observed responsibilities in `pipeline.py`:

- pre-fetch checks
- fetch result classification
- HTML parse orchestration
- RSS/Atom feed parse orchestration
- indexer submission
- discovered outlink admission
- crawl attempt logging and URL status updates

The module is not only worker orchestration. It is also the central crawl
processing pipeline.

## Impact

Future changes can become harder to place and review because unrelated crawler
concerns are close together in one worker-named module.

This is already visible around feed handling: adding feed entry ledger behavior
would touch the same module that also handles HTML parsing, indexing, and crawl
attempt recording.

## Direction

Do not perform a broad package or directory restructure just to make the path
look cleaner.

When active fixes touch this area, prefer small responsibility cuts around the
changed behavior. Possible future cuts include:

- feed result processing
- discovered URL admission helpers
- indexer submission helpers
- fetch result classification

Keep worker orchestration separate from crawl-processing logic only when a
specific change makes the split useful.

## Progress

RSS/Atom feed result processing has been moved out of `workers/pipeline.py` into
`services/feed_processing.py`.

HTML result processing has been moved out of `workers/pipeline.py` into
`services/html_processing.py`.

Shared crawler processing types now live in `workers/types.py`, and shared
timing helpers live in `workers/timing.py`.

Discovered URL admission now lives in `services/url_discovery.py`.

The remaining issue is narrower: `pipeline.py` still owns precheck, fetch,
non-HTML handling, generic HTTP error handling, and the top-level fetch-result
dispatch.
