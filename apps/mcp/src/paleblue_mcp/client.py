import httpx

from paleblue_mcp.config import settings


class PaleBlueClient:
    """HTTP client for PaleBlueSearch API."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.base_url
        self.timeout = settings.timeout

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "paleblue-mcp/1.0"}

    async def search(
        self,
        query: str,
        limit: int = 10,
        page: int = 1,
        mode: str = "bm25",
        include_content: bool = False,
    ) -> dict:
        params: dict = {"q": query, "limit": limit, "page": page, "mode": mode}
        if include_content:
            params["include_content"] = "true"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/search",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_content(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/content",
                params={"url": url},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
