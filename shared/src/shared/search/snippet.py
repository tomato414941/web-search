"""
Snippet Generation for Search Results

Generates KWIC (Key Word In Context) snippets with term highlighting.
"""

import re
from dataclasses import dataclass


@dataclass
class Snippet:
    """A text snippet with optional highlighting."""

    text: str  # The snippet text (may include HTML <mark> tags)
    plain_text: str  # The snippet without HTML tags


def generate_snippet(
    text: str,
    terms: list[str],
    window_size: int = 150,
    highlight: bool = True,
) -> Snippet:
    """
    Generate a snippet with highlighted terms using KWIC (Key Word In Context).

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

    # 3. Choose best match (first occurrence)
    best_match = matches[0]
    start_pos = best_match.start()

    # 4. Extract context window around the match
    half_window = window_size // 2
    snippet_start = max(0, start_pos - half_window)
    snippet_end = min(len(text), start_pos + half_window)

    # Adjust to avoid cutting words
    if snippet_start > 0:
        space_pos = text.rfind(" ", 0, snippet_start + 20)
        if space_pos != -1 and space_pos > snippet_start - 20:
            snippet_start = space_pos + 1

    if snippet_end < len(text):
        space_pos = text.find(" ", snippet_end - 20)
        if space_pos != -1 and space_pos < snippet_end + 20:
            snippet_end = space_pos

    snippet = text[snippet_start:snippet_end].strip()

    # 5. Add ellipsis if needed
    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < len(text):
        snippet = snippet + "..."

    plain_text = snippet

    # 6. Highlight all terms in the snippet (if requested)
    if highlight:
        def replace_fn(match):
            return f"<mark>{match.group(0)}</mark>"

        highlighted = pattern.sub(replace_fn, snippet)
        return Snippet(text=highlighted, plain_text=plain_text)

    return Snippet(text=plain_text, plain_text=plain_text)


def highlight_snippet(text: str, terms: list[str], window_size: int = 150) -> str:
    """
    Convenience function that returns just the highlighted HTML string.

    This is a drop-in replacement for the original frontend function.
    """
    snippet = generate_snippet(text, terms, window_size, highlight=True)
    return snippet.text
