"""
HTML Parser Utilities

Functions for extracting content and links from HTML.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

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


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", _strip_nul(text)).strip()


def _is_homepage(url: str) -> bool:
    path = urlparse(url).path or "/"
    return path in {"", "/"}


def _extract_meta_description(soup: BeautifulSoup) -> str:
    selectors = (
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    )
    for attrs in selectors:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return _normalize_space(tag["content"])
    return ""


def _extract_heading_text(
    soup: BeautifulSoup, names: tuple[str, ...], limit: int
) -> list[str]:
    values: list[str] = []
    for tag in soup.find_all(names):
        text = _normalize_space(tag.get_text(" ", strip=True))
        if not text or text in values:
            continue
        values.append(text)
        if len(values) >= limit:
            break
    return values


def _build_homepage_search_fallback(soup: BeautifulSoup, title: str) -> str:
    parts: list[str] = []
    for value in (
        _normalize_space(title),
        _extract_meta_description(soup),
        *_extract_heading_text(soup, ("h1",), limit=2),
        *_extract_heading_text(soup, ("h2", "h3"), limit=6),
    ):
        if not value or value in parts:
            continue
        parts.append(value)
    return " ".join(parts)


def _maybe_enrich_homepage_text(
    text: str, soup: BeautifulSoup, title: str, url: str
) -> str:
    if not _is_homepage(url):
        return text
    if len(text.split()) >= 40:
        return text

    fallback = _build_homepage_search_fallback(soup, title)
    if not fallback:
        return text
    if not text:
        return fallback
    if fallback in text:
        return text
    return _normalize_space(f"{text} {fallback}")


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


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _find_child_text(element: ET.Element, names: tuple[str, ...]) -> str | None:
    for child in element:
        if _local_name(child.tag) not in names:
            continue
        text = _normalize_space("".join(child.itertext()))
        if text:
            return text
    return None


def _find_atom_link(element: ET.Element) -> str | None:
    for child in element:
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").strip().lower()
        if href and rel in {"", "alternate"}:
            return href
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
    updated_at: str | None = None
    outlinks: list[str] | None = None
    feed_links: list[str] | None = None


@dataclass(frozen=True)
class FeedEntry:
    url: str
    title: str
    content: str


def parse_page(html: str, base_url: str, max_outlinks: int = 100) -> ParsedDocument:
    """Parse HTML in a single pass: extract metadata, content, and links.

    Avoids double-parsing by reusing one BeautifulSoup instance for both
    metadata extraction and link discovery. Uses lxml for speed.
    """
    from web_search_core.utils import normalize_url

    cleaned_html = _strip_nul(html)
    soup = BeautifulSoup(cleaned_html, "lxml")

    title = ""
    if soup.title and soup.title.string:
        title = _strip_nul(soup.title.string).strip()

    # Extract metadata BEFORE decomposing script tags
    updated_at = extract_updated_at(soup)

    # Main content via trafilatura (uses raw HTML, not soup)
    text = trafilatura.extract(
        cleaned_html,
        include_comments=True,
        include_tables=True,
        deduplicate=True,
        favor_recall=True,
    )

    if text:
        text = _normalize_space(text)
    else:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = _normalize_space(text)

    text = _maybe_enrich_homepage_text(text, soup, title, base_url)

    # Extract links from the same soup (already parsed)
    outlinks: list[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if isinstance(href, list):
            href = href[0] if href else None
        u = normalize_url(base_url, href, block_private=True)
        if u:
            outlinks.append(u)
        if len(outlinks) >= max_outlinks:
            break

    feed_links: list[str] = []
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel_values = {part.strip().lower() for part in rel.split()}
        else:
            rel_values = {str(part).strip().lower() for part in rel}
        if "alternate" not in rel_values:
            continue

        link_type = str(link.get("type") or "").strip().lower()
        if link_type not in {"application/rss+xml", "application/atom+xml"}:
            continue

        href = link.get("href")
        if isinstance(href, list):
            href = href[0] if href else None
        u = normalize_url(base_url, href, block_private=True)
        if u and u not in feed_links:
            feed_links.append(u)

    return ParsedDocument(
        title=title,
        content=text,
        updated_at=updated_at,
        outlinks=outlinks,
        feed_links=feed_links,
    )


def parse_feed(xml_text: str) -> list[FeedEntry]:
    root = ET.fromstring(xml_text)
    entries: list[FeedEntry] = []

    for element in root.iter():
        local_name = _local_name(element.tag)
        if local_name not in {"item", "entry"}:
            continue

        title = _find_child_text(element, ("title",))
        content = _find_child_text(
            element, ("description", "summary", "content", "encoded")
        )
        if local_name == "item":
            url = _find_child_text(element, ("link", "guid"))
        else:
            url = _find_atom_link(element) or _find_child_text(element, ("id",))
        if not title or not url or not content:
            continue

        entries.append(
            FeedEntry(
                url=url,
                title=title,
                content=content,
            )
        )

    deduped: list[FeedEntry] = []
    seen_urls: set[str] = set()
    for entry in entries:
        if entry.url in seen_urls:
            continue
        seen_urls.add(entry.url)
        deduped.append(entry)
    return deduped
