# HTML Storage Design (Cloudflare R2)

> Status: design note only. This document describes a possible future direction and is not implemented in the current runtime.

## Problem

Raw HTML is discarded after text extraction. When we improve extraction logic
(e.g. trafilatura, content quality), we must re-crawl large parts of the corpus to
apply changes. This wastes bandwidth, time, and is unfriendly to target sites.

## Solution

Store raw HTML in Cloudflare R2 (S3-compatible) immediately after fetch,
before parsing. This enables offline re-processing without re-crawling.

## Architecture

```
fetch() → result.body (HTML str)
    │
    ├── store_html(url, html)  ← async, best-effort
    │       ↓
    │   R2: html/{url_sha256}.html.gz
    │
    ├── parse(html) → ParseResult
    │
    └── submit_to_indexer(parsed)
```

## R2 Object Layout

```
bucket: palebluesearch-html
prefix: html/

Key format:  html/{sha256(url)}.html.gz
Example:     html/a1b2c3d4e5f6...7890.html.gz
```

- SHA256 hash of URL as key (deterministic, no collisions, no encoding issues)
- gzip compressed (avg 7x compression: 100KB → 15KB)
- Flat namespace (no date/domain hierarchy — simpler, easier to purge)

## Metadata

R2 supports custom metadata headers on objects:

```
x-amz-meta-url: https://example.com/page
x-amz-meta-fetched-at: 2026-03-02T12:00:00Z
x-amz-meta-content-type: text/html; charset=utf-8
x-amz-meta-status-code: 200
```

This allows looking up the original URL and fetch timestamp without
maintaining a separate index.

## Cost Estimate

| Metric | Value | Cost |
|--------|-------|------|
| Pages | 600K (growing) | — |
| Avg HTML size | ~100KB | — |
| Avg gzip size | ~15KB | — |
| Total storage | ~9GB | **$0.14/mo** |
| Write ops (Class A) | $4.50/1M | **$2.70** initial |
| Read ops (Class B) | $0.36/1M | on-demand |
| Egress | — | **Free** |

## Implementation

### Configuration

New env vars in crawler config:

```
HTML_STORE_ENABLED=true
HTML_STORE_BUCKET=palebluesearch-html
HTML_STORE_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
HTML_STORE_ACCESS_KEY=...
HTML_STORE_SECRET_KEY=...
```

Store credentials in `~/.secrets/r2`.

### Storage Module

New file: `crawler/src/app/services/html_store.py`

```python
import gzip
import hashlib
import logging
from io import BytesIO

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)


class HtmlStore:
    def __init__(self, endpoint: str, bucket: str,
                 access_key: str, secret_key: str):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(retries={"max_attempts": 1}),
        )

    def store(self, url: str, html: str, fetched_at: str) -> None:
        key = f"html/{hashlib.sha256(url.encode()).hexdigest()}.html.gz"
        body = gzip.compress(html.encode("utf-8"))
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentEncoding="gzip",
            ContentType="text/html",
            Metadata={
                "url": url[:1024],
                "fetched-at": fetched_at,
            },
        )

    def fetch(self, url: str) -> str | None:
        key = f"html/{hashlib.sha256(url.encode()).hexdigest()}.html.gz"
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            return gzip.decompress(resp["Body"].read()).decode("utf-8")
        except self.client.exceptions.NoSuchKey:
            return None
```

### Pipeline Integration

In `pipeline.py`, add after fetch succeeds:

```python
async def store_html(ctx: PipelineContext, html: str) -> None:
    """Store raw HTML to R2 (best-effort, non-blocking)."""
    if not ctx.html_store:
        return
    try:
        loop = asyncio.get_running_loop()
        now = datetime.now(timezone.utc).isoformat()
        await loop.run_in_executor(
            None, ctx.html_store.store, ctx.url, html, now
        )
    except Exception:
        logger.debug("HTML store failed for %s", ctx.url, exc_info=True)
```

In `tasks.py` process_url, after fetch succeeds:

```python
# Stage 2: Fetch
result = await fetch(ctx)
if result.body:
    # Store raw HTML (best-effort)
    await store_html(ctx, result.body)

# Stage 3: Parse
parsed = await parse(result.body, url, ...)
```

### Re-processing Script

For offline re-processing (e.g. after improving trafilatura config):

```
scripts/ops/reprocess_html.py --bucket palebluesearch-html \
    --indexer-url http://indexer:8000 \
    --batch-size 100
```

This script:
1. Lists all objects in the R2 bucket
2. Downloads and decompresses HTML
3. Runs html_to_doc() with current extraction logic
4. Submits to indexer API

## Rollout Plan

1. Create R2 bucket via Cloudflare dashboard
2. Generate API token with read/write permissions
3. Store credentials in `~/.secrets/r2`
4. Add `boto3` to crawler requirements
5. Implement html_store.py
6. Integrate into pipeline (behind HTML_STORE_ENABLED flag)
7. Deploy to STG, verify objects appear in R2
8. Deploy to PRD

## Future Enhancements

- Lifecycle policy: delete HTML older than 90 days (if storage grows)
- Batch re-processing with parallelism
- Store HTTP headers alongside HTML (for content negotiation debugging)
