"""
HTML Parser Utilities

Functions for extracting content and links from HTML.
"""

import re
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
import warnings

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def _strip_nul(text: str) -> str:
    return text.replace("\x00", " ")


def html_to_doc(html: str) -> tuple[str, str]:
    """
    Extract (title, text) from HTML using BeautifulSoup.

    Simplified version without trafilatura for better performance.
    Removes script, style, and noscript tags, then extracts all text.

    Args:
        html: Raw HTML string

    Returns:
        Tuple of (title, text_content)
    """
    soup = BeautifulSoup(_strip_nul(html), "html.parser")

    # Extract title
    title = ""
    if soup.title and soup.title.string:
        title = _strip_nul(soup.title.string).strip()

    # Remove unwanted tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Extract text
    text = soup.get_text(" ", strip=True)
    text = _strip_nul(text)
    text = re.sub(r"\s+", " ", text).strip()

    return title, text


def extract_links(base_url: str, html: str, limit: int = 100) -> list[str]:
    """
    Extract absolute links from HTML.

    Args:
        base_url: Base URL for resolving relative links
        html: Raw HTML string
        limit: Maximum number of links to extract

    Returns:
        List of absolute URLs
    """
    from shared.core.utils import normalize_url

    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if isinstance(href, list):
            href = href[0] if href else None
        u = normalize_url(base_url, href)
        if u:
            urls.append(u)
        if len(urls) >= limit:
            break
    return urls
