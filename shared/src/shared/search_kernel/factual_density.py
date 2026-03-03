"""Factual Density scoring for AI-agent-optimized ranking.

Measures verifiable facts per unit of text, NOT just text volume.
Replaces the shallow content_quality score (word_count + link_density).

Positive signals: named entities, numbers, dates, citations, code/tables
Negative signals: vague language, link-heavy aggregation
"""

import re

# --- Positive signals ---

# Numbers: integers, decimals, percentages, measurements
_NUMBER_RE = re.compile(r"\b\d[\d,.]*(?:%|px|ms|kb|mb|gb|tb|hz|ghz)?\b", re.IGNORECASE)

# Dates: ISO-like, slash-separated, written months
_DATE_RE = re.compile(
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)

# URLs and references
_URL_RE = re.compile(r"https?://\S+")
_CITATION_RE = re.compile(r"\[\d+\]|\(\d{4}\)|\((?:et al\.?,?\s*)?\d{4}\)")

# Code indicators
_CODE_RE = re.compile(
    r"```|<code>|<pre>"
    r"|\bdef\s+\w+\s*\("
    r"|\bclass\s+\w+[\s(:]"
    r"|\bfunction\s+\w+\s*\("
    r"|\bimport\s+\w+"
    r"|\bconst\s+\w+\s*="
    r"|\blet\s+\w+\s*="
)

# Capitalized sequences (potential named entities)
_NAMED_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")

# --- Negative signals (vague language) ---

_VAGUE_EN = re.compile(
    r"\b(?:"
    r"it is said|it's said|it is believed|it's believed"
    r"|generally|probably|perhaps|maybe"
    r"|some people|many people|some experts|many experts"
    r"|in general|tends to|it seems"
    r"|as we all know|everyone knows"
    r"|reportedly|allegedly|supposedly"
    r")\b",
    re.IGNORECASE,
)

_VAGUE_JA = re.compile(
    r"(?:"
    r"と言われている|とされている|らしい|かもしれない"
    r"|一般的に|おそらく|たぶん"
    r"|と考えられている|と思われる"
    r"|みんな知っている|周知のとおり"
    r")"
)


def compute_factual_density(
    content: str,
    outlinks_count: int = 0,
    word_count: int = 0,
) -> float:
    """Compute factual density score (0.0-1.0).

    Measures the density of verifiable, specific information per unit of text.
    AI agents need pages rich in facts, not just long text.
    """
    if not content or word_count == 0:
        return 0.0

    text_len = len(content)
    if text_len < 50:
        return 0.0

    # --- Positive signal densities (per 1000 chars) ---
    per_k = 1000.0 / text_len

    number_count = len(_NUMBER_RE.findall(content))
    date_count = len(_DATE_RE.findall(content))
    url_count = len(_URL_RE.findall(content))
    citation_count = len(_CITATION_RE.findall(content))
    code_count = len(_CODE_RE.findall(content))
    entity_count = len(_NAMED_ENTITY_RE.findall(content))

    # Weighted fact score (normalized per 1000 chars)
    fact_score = (
        number_count * 1.0
        + date_count * 2.0
        + url_count * 1.5
        + citation_count * 3.0
        + code_count * 2.0
        + entity_count * 1.0
    ) * per_k

    # Normalize to 0-1 range (10 facts per 1000 chars -> 1.0)
    positive = min(1.0, fact_score / 10.0)

    # --- Negative signal density ---
    vague_en = len(_VAGUE_EN.findall(content))
    vague_ja = len(_VAGUE_JA.findall(content))
    vague_total = vague_en + vague_ja
    vague_density = vague_total * per_k

    # Penalty: 3+ vague expressions per 1000 chars -> 0.5 penalty
    negative = max(0.5, 1.0 - vague_density / 6.0)

    # --- Link density penalty ---
    if word_count > 0 and outlinks_count > 0:
        link_ratio = outlinks_count / word_count
        # Heavy linking (>0.1 links per word) = aggregation page
        link_penalty = max(0.3, 1.0 - link_ratio * 5)
    else:
        link_penalty = 1.0

    # --- Substance floor ---
    # Very short content gets a floor penalty
    substance = min(1.0, word_count / 200.0)

    score = positive * negative * link_penalty * substance
    return round(min(1.0, max(0.0, score)), 4)
