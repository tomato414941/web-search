"""
System Router

Provides canonical health check endpoints:
- /health: Simple health for load balancers
- /readyz: Readiness probe (dependencies healthy)
"""

import asyncio
import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from web_search_frontend.core.config import settings
from web_search_postgres.search import ensure_db

# Router for root-level health endpoints
root_router = APIRouter()


def _check_database() -> bool:
    """Check database connectivity."""
    try:
        ensure_db()
        return True
    except Exception:
        return False


def _check_opensearch() -> dict:
    """Check OpenSearch connectivity and document count."""
    try:
        from web_search_opensearch.client import get_client, index_name

        from web_search_opensearch.mapping import validate_index, SEARCH_PIPELINE

        client = get_client(settings.OPENSEARCH_URL)
        validate_index(client)
        client.transport.perform_request("GET", f"/_search/pipeline/{SEARCH_PIPELINE}")
        count = client.count(index=index_name())["count"]
        return {"status": "ok", "documents": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _get_readiness_response():
    db_ok, opensearch = await asyncio.gather(
        asyncio.to_thread(_check_database),
        asyncio.to_thread(_check_opensearch),
    )
    embeddings_configured = bool(os.environ.get("OPENAI_API_KEY"))
    ok = db_ok and opensearch["status"] == "ok" and embeddings_configured
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ok" if ok else "unhealthy",
            "checks": {
                "database": "ok" if db_ok else "unhealthy",
                "opensearch": opensearch,
                "embeddings": "configured"
                if embeddings_configured
                else "missing_api_key",
            },
        },
    )


ROBOTS_TXT = """\
User-agent: *
Allow: /
Disallow: /api/
Sitemap: https://palebluesearch.com/sitemap.xml
"""

SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://palebluesearch.com/</loc></url>
</urlset>
"""


# --- SEO endpoints ---


@root_router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return PlainTextResponse(ROBOTS_TXT, media_type="text/plain")


@root_router.get("/sitemap.xml")
async def sitemap_xml():
    return Response(content=SITEMAP_XML, media_type="application/xml")


# --- Root-level endpoints ---


@root_router.get("/health")
async def health():
    """Simple health check for load balancers."""
    return {"status": "ok"}


@root_router.get("/readyz")
async def readyz():
    """Readiness probe for dependency health."""
    return await _get_readiness_response()
