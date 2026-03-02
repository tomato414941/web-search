"""
HTML Parser Utilities

Functions for extracting content and links from HTML.
"""

import json
import re
from datetime import datetime, timezone

import trafilatura
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
import warnings

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _strip_nul(text: str) -> str:
    return text.replace("\x00", " ")


def _parse_date(raw: str) -> str | None:
    """Parse date string to ISO 8601, rejecting future dates."""
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > datetime.now(timezone.utc):
                return None
            return dt.isoformat()
        except ValueError:
            continue
    return None


def extract_published_at(soup: BeautifulSoup) -> str | None:
    """Extract published date from HTML metadata.

    Priority:
    1. <meta property="article:published_time">
    2. JSON-LD datePublished
    3. <meta name="date">
    4. <meta name="DC.date">
    5. <time datetime="...">
    """
    raw = None

    tag = soup.find("meta", attrs={"property": "article:published_time"})
    if tag and tag.get("content"):
        raw = tag["content"]

    if raw is None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and "datePublished" in data:
                    raw = data["datePublished"]
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "datePublished" in item:
                            raw = item["datePublished"]
                            break
            except (json.JSONDecodeError, TypeError):
                continue
            if raw:
                break

    if raw is None:
        tag = soup.find("meta", attrs={"name": "date"})
        if tag and tag.get("content"):
            raw = tag["content"]

    if raw is None:
        tag = soup.find("meta", attrs={"name": "DC.date"})
        if tag and tag.get("content"):
            raw = tag["content"]

    if raw is None:
        tag = soup.find("time", attrs={"pubdate": True})
        if not tag:
            tag = soup.find("time", attrs={"datetime": True})
        if tag and tag.get("datetime"):
            raw = tag["datetime"]

    if raw is None:
        return None

    return _parse_date(raw.strip())


def html_to_doc(html: str) -> tuple[str, str, str | None]:
    """Extract (title, text, published_at) from HTML.

    Primary: trafilatura for boilerplate-free main content extraction.
    Fallback: BeautifulSoup get_text() when trafilatura returns None.

    Returns:
        Tuple of (title, text_content, published_at_iso)
    """
    cleaned_html = _strip_nul(html)

    # Title and published_at always via BeautifulSoup
    soup = BeautifulSoup(cleaned_html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = _strip_nul(soup.title.string).strip()

    # Extract published_at BEFORE decomposing script tags
    published_at = extract_published_at(soup)

    # Main content: try trafilatura first
    text = trafilatura.extract(
        cleaned_html,
        include_comments=True,
        include_tables=True,
        deduplicate=True,
        favor_recall=True,
    )

    if text:
        text = _strip_nul(text)
        text = re.sub(r"\s+", " ", text).strip()
    else:
        # Fallback: BeautifulSoup full-text extraction
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = _strip_nul(text)
        text = re.sub(r"\s+", " ", text).strip()

    return title, text, published_at


def extract_links(base_url: str, html: str, limit: int = 100) -> list[str]:
    """Extract absolute links from HTML."""
    from shared.core.utils import normalize_url

    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if isinstance(href, list):
            href = href[0] if href else None
        u = normalize_url(base_url, href, block_private=True)
        if u:
            urls.append(u)
        if len(urls) >= limit:
            break
    return urls
