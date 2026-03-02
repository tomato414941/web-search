import httpx

from paleblue_mcp.config import settings


class PaleBlueClient:
    """HTTP client for PaleBlueSearch API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or settings.base_url
        self.api_key = api_key if api_key is not None else settings.api_key
        self.timeout = settings.timeout

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "paleblue-mcp/1.0"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def search(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
        mode: str = "auto",
    ) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/search",
                params={"q": query, "limit": limit, "page": page, "mode": mode},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_stats(self) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/stats",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
