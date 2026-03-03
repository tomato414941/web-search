"""
HTML Parser Utilities

Functions for extracting content and links from HTML.
"""

import json
import re
from dataclasses import dataclass
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


def extract_author(soup: BeautifulSoup) -> str | None:
    """Extract author name from HTML metadata.

    Priority:
    1. <meta name="author">
    2. JSON-LD author.name
    3. <meta property="article:author">
    4. <a rel="author">
    """
    tag = soup.find("meta", attrs={"name": "author"})
    if tag and tag.get("content"):
        name = tag["content"].strip()
        if name:
            return name

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            if isinstance(data, dict):
                author = data.get("author")
                if isinstance(author, dict) and author.get("name"):
                    return author["name"].strip()
                if isinstance(author, list) and author:
                    first = author[0]
                    if isinstance(first, dict) and first.get("name"):
                        return first["name"].strip()
                    if isinstance(first, str) and first.strip():
                        return first.strip()
                if isinstance(author, str) and author.strip():
                    return author.strip()
        except (json.JSONDecodeError, TypeError):
            continue

    tag = soup.find("meta", attrs={"property": "article:author"})
    if tag and tag.get("content"):
        name = tag["content"].strip()
        if name:
            return name

    tag = soup.find("a", attrs={"rel": "author"})
    if tag and tag.get_text(strip=True):
        return tag.get_text(strip=True)

    return None


def extract_organization(soup: BeautifulSoup) -> str | None:
    """Extract organization/publisher from HTML metadata.

    Priority:
    1. JSON-LD publisher.name
    2. <meta property="og:site_name">
    3. <meta name="publisher">
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            if isinstance(data, dict):
                publisher = data.get("publisher")
                if isinstance(publisher, dict) and publisher.get("name"):
                    return publisher["name"].strip()
        except (json.JSONDecodeError, TypeError):
            continue

    tag = soup.find("meta", attrs={"property": "og:site_name"})
    if tag and tag.get("content"):
        name = tag["content"].strip()
        if name:
            return name

    tag = soup.find("meta", attrs={"name": "publisher"})
    if tag and tag.get("content"):
        name = tag["content"].strip()
        if name:
            return name

    return None


def extract_updated_at(soup: BeautifulSoup) -> str | None:
    """Extract last modified date from HTML metadata.

    Priority:
    1. <meta property="article:modified_time">
    2. JSON-LD dateModified
    3. <meta http-equiv="last-modified">
    """
    tag = soup.find("meta", attrs={"property": "article:modified_time"})
    if tag and tag.get("content"):
        result = _parse_date(tag["content"].strip())
        if result:
            return result

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            if isinstance(data, dict) and "dateModified" in data:
                result = _parse_date(data["dateModified"].strip())
                if result:
                    return result
        except (json.JSONDecodeError, TypeError):
            continue

    tag = soup.find("meta", attrs={"http-equiv": "last-modified"})
    if tag and tag.get("content"):
        result = _parse_date(tag["content"].strip())
        if result:
            return result

    return None


@dataclass
class ParsedDocument:
    """Full extraction result from HTML parsing."""

    title: str
    content: str
    published_at: str | None = None
    updated_at: str | None = None
    author: str | None = None
    organization: str | None = None


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


def html_to_doc_full(html: str) -> ParsedDocument:
    """Extract full metadata from HTML including author/org/updated_at.

    Returns a ParsedDocument with all available metadata.
    """
    cleaned_html = _strip_nul(html)
    soup = BeautifulSoup(cleaned_html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = _strip_nul(soup.title.string).strip()

    # Extract metadata BEFORE decomposing script tags
    published_at = extract_published_at(soup)
    updated_at = extract_updated_at(soup)
    author = extract_author(soup)
    organization = extract_organization(soup)

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
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = _strip_nul(text)
        text = re.sub(r"\s+", " ", text).strip()

    return ParsedDocument(
        title=title,
        content=text,
        published_at=published_at,
        updated_at=updated_at,
        author=author,
        organization=organization,
    )


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
