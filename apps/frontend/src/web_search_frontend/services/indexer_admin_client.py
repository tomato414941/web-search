import logging
from typing import Any

import httpx

from web_search_frontend.core.config import settings
from web_search_contracts.admin_read_models import IndexerJobSummaryReadModel

logger = logging.getLogger(__name__)


def _default_job_summary() -> dict[str, Any]:
    return IndexerJobSummaryReadModel().model_dump(mode="json")


async def fetch_indexer_job_summary() -> dict[str, Any]:
    """
    Fetch indexer job summary from the internal indexer service.

    This call is server-side only to avoid exposing API keys in the browser.
    """
    result = _default_job_summary()

    if not settings.INDEXER_API_KEY:
        result["error"] = "missing INDEXER_API_KEY"
        return IndexerJobSummaryReadModel.model_validate(result).model_dump(mode="json")

    base_url = (settings.INDEXER_SERVICE_URL or "").rstrip("/")
    if not base_url:
        result["error"] = "missing INDEXER_SERVICE_URL"
        return IndexerJobSummaryReadModel.model_validate(result).model_dump(mode="json")

    url = f"{base_url}/api/v1/indexer/job-summary"
    headers = {"X-API-Key": settings.INDEXER_API_KEY}
    try:
        async with httpx.AsyncClient(
            timeout=settings.INDEXER_ADMIN_TIMEOUT_SEC
        ) as client:
            resp = await client.get(url, headers=headers)
            result["http_status"] = resp.status_code
            if resp.status_code != 200:
                result["error"] = f"indexer returned {resp.status_code}"
                return IndexerJobSummaryReadModel.model_validate(result).model_dump(
                    mode="json"
                )

            data = resp.json()
            result["reachable"] = True
            result["ok"] = bool(data.get("ok"))
            for key in ("failed_permanent_jobs",):
                if key in data and data.get(key) is not None:
                    result[key] = data[key]
    except Exception as exc:
        logger.warning("Failed to fetch indexer job summary: %s", exc)
        result["error"] = str(exc)

    return IndexerJobSummaryReadModel.model_validate(result).model_dump(mode="json")
