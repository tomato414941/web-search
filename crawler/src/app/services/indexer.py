"""
Indexer Service

Submits crawled pages to the Indexer API.
"""

import logging
import aiohttp

logger = logging.getLogger(__name__)


async def submit_page_to_indexer(
    session: aiohttp.ClientSession,
    api_url: str,
    api_key: str,
    url: str,
    title: str,
    content: str,
) -> bool:
    """
    Submit a page to the Indexer API

    Args:
        session: aiohttp client session
        api_url: Full URL to indexer endpoint
        api_key: API key for authentication
        url: Page URL
        title: Page title
        content: Page content

    Returns:
        True if successful, False otherwise
    """
    try:
        headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "url": url,
            "title": title,
            "content": content,
        }

        async with session.post(
            api_url, json=payload, headers=headers, timeout=60
        ) as resp:
            if resp.status == 200:
                logger.info(f"✅ Indexed: {url}")
                return True
            else:
                error_text = await resp.text()
                logger.error(f"❌ API error {resp.status} for {url}: {error_text}")
                return False

    except Exception as e:
        logger.error(f"❌ Failed to submit {url} to API: {e}")
        return False
