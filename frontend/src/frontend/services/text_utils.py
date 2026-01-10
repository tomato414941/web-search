"""
Text Processing Utilities

Frontend-specific text processing, including HTML snippet generation.
"""
import re


def highlight_snippet(text: str, terms: list[str], window_size: int = 150) -> str:
    """
    Generate a snippet with highlighted terms using KWIC (Key Word In Context).
    
    Args:
        text: The original text content.
        terms: List of query terms to highlight.
        window_size: Approximate size of the snippet window.
        
    Returns:
        HTML string with <mark> tags highlighting the terms
    """
    if not text:
        return ""
    if not terms:
        return text[:window_size] + "..."

    # 1. Prepare Regex for all terms (case-insensitive)
    # Escape terms to avoid regex errors
    escaped_terms = [re.escape(t) for t in terms if t.strip()]
    if not escaped_terms:
        return text[:window_size] + "..."

    pattern = re.compile(r"(" + "|".join(escaped_terms) + r")", re.IGNORECASE)

    # 2. Find all matches
    matches = list(pattern.finditer(text))
    if not matches:
        return text[:window_size] + "..."

    # 3. Choose best match (first occurrence)
    best_match = matches[0]
    start_pos = best_match.start()

    # 4. Extract context window around the match
    # Calculate start and end of the window
    half_window = window_size // 2
    snippet_start = max(0, start_pos - half_window)
    snippet_end = min(len(text), start_pos + half_window)

    # Adjust to avoid cutting words
    # Move snippet_start to the nearest space if not at the beginning
    if snippet_start > 0:
        space_pos = text.rfind(" ", 0, snippet_start + 20)
        if space_pos != -1 and space_pos > snippet_start - 20:
            snippet_start = space_pos + 1

    # Move snippet_end to the nearest space if not at the end
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

    # 6. Highlight all terms in the snippet
    def replace_fn(match):
        return f"<mark>{match.group(0)}</mark>"

    highlighted = pattern.sub(replace_fn, snippet)

    return highlighted
