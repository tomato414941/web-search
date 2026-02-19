"""
Snippet Generation for Search Results

Generates KWIC (Key Word In Context) snippets with term highlighting.
Uses best-window selection (highest distinct term density) and
Japanese sentence boundary detection.
"""

import html
import re
from dataclasses import dataclass

# Japanese sentence boundaries
_JA_BOUNDARY_RE = re.compile(r"[。！？\n]")


@dataclass
class Snippet:
    """A text snippet with optional highlighting."""

    text: str  # The snippet text (may include HTML <mark> tags)
    plain_text: str  # The snippet without HTML tags


def _find_best_window(
    text: str,
    matches: list[re.Match],
    escaped_terms: list[str],
    half_window: int,
) -> int:
    """Find the window center with the highest distinct term density."""
    best_start = matches[0].start()
    best_score = 0

    for match in matches:
        center = match.start()
        w_start = max(0, center - half_window)
        w_end = min(len(text), center + half_window)
        window_text = text[w_start:w_end]

        distinct = sum(
            1 for t in escaped_terms if re.search(t, window_text, re.IGNORECASE)
        )
        if distinct > best_score:
            best_score = distinct
            best_start = w_start

    return best_start


def _snap_to_boundary(text: str, pos: int, search_range: int = 30) -> int:
    """Snap position to nearest sentence boundary (JA or space)."""
    lo = max(0, pos - search_range)
    hi = min(len(text), pos + search_range)
    region = text[lo:hi]

    ja_match = _JA_BOUNDARY_RE.search(region)
    if ja_match:
        return lo + ja_match.end()

    space_pos = text.rfind(" ", lo, hi)
    if space_pos != -1:
        return space_pos + 1

    return pos


def generate_snippet(
    text: str,
    terms: list[str],
    window_size: int = 200,
    highlight: bool = True,
) -> Snippet:
    """
    Generate a snippet with highlighted terms using KWIC (Key Word In Context).

    Selects the window with the highest distinct term density rather than
    the first match. Uses Japanese sentence boundaries when available.

    Args:
        text: The original text content.
        terms: List of query terms to highlight.
        window_size: Approximate size of the snippet window.
        highlight: Whether to add <mark> tags for highlighting.

    Returns:
        Snippet object with text and plain_text
    """
    if not text:
        return Snippet(text="", plain_text="")

    if not terms:
        plain = text[:window_size] + "..." if len(text) > window_size else text
        return Snippet(text=plain, plain_text=plain)

    # 1. Prepare Regex for all terms (case-insensitive)
    escaped_terms = [re.escape(t) for t in terms if t.strip()]
    if not escaped_terms:
        plain = text[:window_size] + "..." if len(text) > window_size else text
        return Snippet(text=plain, plain_text=plain)

    pattern = re.compile(r"(" + "|".join(escaped_terms) + r")", re.IGNORECASE)

    # 2. Find all matches
    matches = list(pattern.finditer(text))
    if not matches:
        plain = text[:window_size] + "..." if len(text) > window_size else text
        return Snippet(text=plain, plain_text=plain)

    # 3. Find best window (highest distinct term density)
    half_window = window_size // 2
    snippet_start = _find_best_window(text, matches, escaped_terms, half_window)
    snippet_end = min(len(text), snippet_start + window_size)

    # 4. Adjust to sentence/word boundaries
    if snippet_start > 0:
        snippet_start = _snap_to_boundary(text, snippet_start)

    if snippet_end < len(text):
        # For end boundary, look for sentence end nearby
        lo = max(snippet_start, snippet_end - 30)
        hi = min(len(text), snippet_end + 30)
        region = text[lo:hi]
        ja_match = _JA_BOUNDARY_RE.search(region)
        if ja_match:
            snippet_end = lo + ja_match.end()
        else:
            space_pos = text.find(" ", snippet_end - 20, snippet_end + 20)
            if space_pos != -1:
                snippet_end = space_pos

    snippet_text = text[snippet_start:snippet_end].strip()

    # 5. Add ellipsis if needed
    if snippet_start > 0:
        snippet_text = "..." + snippet_text
    if snippet_end < len(text):
        snippet_text = snippet_text + "..."

    plain_text = snippet_text

    # 6. Highlight all terms in the snippet (if requested)
    if highlight:
        parts = pattern.split(snippet_text)  # [non-match, match, non-match, ...]
        result_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                result_parts.append(html.escape(part))
            else:
                result_parts.append(f"<mark>{html.escape(part)}</mark>")
        highlighted = "".join(result_parts)
        return Snippet(text=highlighted, plain_text=plain_text)

    return Snippet(text=plain_text, plain_text=plain_text)


def highlight_snippet(text: str, terms: list[str], window_size: int = 200) -> str:
    """
    Convenience function that returns just the highlighted HTML string.

    This is a drop-in replacement for the original frontend function.
    """
    snippet = generate_snippet(text, terms, window_size, highlight=True)
    return snippet.text
