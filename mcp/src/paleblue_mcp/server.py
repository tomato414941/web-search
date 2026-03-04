import logging
import sys

from mcp.server.fastmcp import FastMCP

from paleblue_mcp.client import PaleBlueClient

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "PaleBlueSearch",
    instructions=(
        "Japanese Web search and content retrieval for AI agents. "
        "Search 1M+ Japanese and English web pages, then fetch full page text "
        "for grounding LLM responses with fresh, sourced information. "
        "Specializes in Japanese tech, news, government, and reference content."
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

    confidence = data.get("confidence")
    perspective_count = data.get("perspective_count")

    header = f"**{total} results** (page {page}/{last_page}, mode: {mode})"
    if confidence:
        header += f" | confidence: {confidence}"
    if perspective_count is not None:
        header += f" | {perspective_count} perspectives"

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
        indexed_at = hit.get("indexed_at", "")
        published_at = hit.get("published_at", "")

        lines.append(f"### {i}. [{title}]({url})")
        if snip:
            lines.append(snip)
        temporal_anchor = hit.get("temporal_anchor")
        origin_type = hit.get("origin_type")
        author = hit.get("author")
        organization = hit.get("organization")
        meta_parts = []
        if origin_type:
            meta_parts.append(f"Origin: {origin_type}")
        if author:
            meta_parts.append(f"Author: {author}")
        if organization:
            meta_parts.append(f"Org: {organization}")
        if published_at:
            meta_parts.append(f"Published: {published_at}")
        if indexed_at:
            meta_parts.append(f"Indexed: {indexed_at}")
        sources_agreeing = hit.get("sources_agreeing")
        if temporal_anchor is not None:
            meta_parts.append(f"Temporal anchor: {temporal_anchor}")
        if sources_agreeing is not None and sources_agreeing > 1:
            meta_parts.append(f"Sources agreeing: {sources_agreeing}")
        if meta_parts:
            lines.append(f"*{' | '.join(meta_parts)}*")

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
    mode: str = "auto",
    page: int = 1,
    include_content: bool = False,
) -> str:
    """Search Japanese and English web pages using PaleBlueSearch.

    Returns fresh web search results with publication and indexing dates.
    Set include_content=true to get full page text inline (useful for RAG).

    Args:
        query: Search query string.
        limit: Number of results (1-50, default 10).
        mode: Search mode - "auto", "bm25", "hybrid", or "semantic".
        page: Page number for pagination (default 1).
        include_content: Include full page text in results (default false).
    """
    limit = max(1, min(limit, 50))
    page = max(1, page)

    try:
        data = await _client.search(
            query=query,
            limit=limit,
            page=page,
            mode=mode,
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
        word_count = data.get("word_count", 0)
        indexed_at = data.get("indexed_at", "")
        published_at = data.get("published_at", "")

        lines = [
            f"# {title}",
            f"URL: {url}",
        ]
        meta_parts = []
        if published_at:
            meta_parts.append(f"Published: {published_at}")
        if indexed_at:
            meta_parts.append(f"Indexed: {indexed_at}")
        if word_count:
            meta_parts.append(f"Words: {word_count}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))
        lines.append("")
        lines.append(content)
        return "\n".join(lines)
    except Exception as e:
        logger.error("Content fetch failed: %s", e)
        return f"Content fetch failed: {e}"


@mcp.tool()
async def get_stats() -> str:
    """Get PaleBlueSearch index statistics.

    Returns the number of indexed pages and crawler queue status.
    """
    try:
        data = await _client.get_stats()
        queue = data.get("queue", {})
        index = data.get("index", {})

        lines = [
            "## PaleBlueSearch Stats",
            f"- **Indexed pages**: {index.get('indexed', 'N/A')}",
            f"- **Queue (pending)**: {queue.get('queued', 'N/A')}",
            f"- **URLs visited**: {queue.get('visited', 'N/A')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.error("Stats failed: %s", e)
        return f"Failed to get stats: {e}"


if __name__ == "__main__":
    mcp.run()
