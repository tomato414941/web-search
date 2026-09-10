import logging
import sys

from mcp.server.fastmcp import FastMCP

from paleblue_mcp.client import PaleBlueClient

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "PaleBlueSearch",
    instructions=(
        "Search Japanese and English web pages and retrieve stored page content."
    ),
)

_client = PaleBlueClient()


def _format_hits(data: dict, include_content: bool = False) -> str:
    """Format search API response as Markdown for LLM consumption."""
    query = data.get("query", "")
    total = data.get("total", 0)
    page = data.get("page", 1)
    last_page = data.get("last_page", 1)
    mode = data.get("mode", "unknown")
    hits = data.get("hits", [])

    header = f"**{total} results** (page {page}/{last_page}, mode: {mode})"

    lines = [
        f"## Search: {query}",
        header,
        "",
    ]

    if not hits:
        lines.append("No results found.")
        return "\n".join(lines)

    for i, hit in enumerate(hits, 1):
        title = hit.get("title") or "Untitled"
        url = hit.get("url", "")
        snip = hit.get("snip_plain", "")

        lines.append(f"### {i}. [{title}]({url})")
        if snip:
            lines.append(snip)

        if include_content and hit.get("content"):
            lines.append("")
            lines.append("**Content:**")
            lines.append(hit["content"])

        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def web_search(
    query: str,
    limit: int = 10,
    page: int = 1,
    include_content: bool = False,
) -> str:
    """Search Japanese and English web pages using PaleBlueSearch.

    Returns hybrid web search results, with up to 200 accessible results.
    Set include_content=true to get the stored search excerpt inline (up to 20,000 characters).

    Args:
        query: Search query string.
        limit: Number of results (1-50, default 10).
        page: Page number for pagination (default 1).
        include_content: Include the stored search excerpt (default false).
    """
    limit = max(1, min(limit, 50))
    page = max(1, page)

    try:
        data = await _client.search(
            query=query,
            limit=limit,
            page=page,
            include_content=include_content,
        )
        return _format_hits(data, include_content=include_content)
    except Exception as e:
        logger.error("Search failed: %s", e)
        return f"Search failed: {e}"


@mcp.tool()
async def fetch_content(url: str) -> str:
    """Fetch the full stored content of a previously indexed page.

    Use this after web_search to get the complete text of a page
    without re-crawling. Ideal for RAG pipelines that need full context.

    Args:
        url: The URL to fetch content for (must be in the index).
    """
    try:
        data = await _client.get_content(url)
        title = data.get("title") or "Untitled"
        content = data.get("content") or ""
        indexed_at = data.get("indexed_at", "")

        lines = [
            f"# {title}",
            f"URL: {url}",
        ]
        meta_parts = []
        if indexed_at:
            meta_parts.append(f"Indexed: {indexed_at}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))
        lines.append("")
        lines.append(content)
        return "\n".join(lines)
    except Exception as e:
        logger.error("Content fetch failed: %s", e)
        return f"Content fetch failed: {e}"


if __name__ == "__main__":
    mcp.run()
