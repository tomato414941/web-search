# Fix: Allow Google Favicons in CSP

## Goal
Enable the display of favicons in search results by updating the Content Security Policy (CSP) to allow image loading from `www.google.com`.

## Problem
The current CSP configuration in `frontend/src/frontend/api/main.py` restricts `img-src` to `'self'` and `data:`. This blocks the browser from loading favicons served by `https://www.google.com/s2/favicons`.

## Proposed Changes

### Frontend Service
#### [MODIFY] [main.py](file:///c:/projects/web-search/frontend/src/frontend/api/main.py)
- Update the `SecurityHeadersMiddleware` class.
- Add `https://www.google.com` to the `img-src` directive in the `Content-Security-Policy` header.

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://www.google.com;"  # Added Google
)
```

## Verification Plan

### Automated Verification
- None (CSP is a runtime header).

### Manual Verification
1. Restart the frontend service.
2. Perform a search (e.g., "test").
3. Inspect the browser console to confirm no CSP violations for `google.com`.
4. Visually confirm that favicons appear next to search results.
