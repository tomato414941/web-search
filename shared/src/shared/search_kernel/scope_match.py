"""Scope Match — query intent vs document type matching.

Matches the "depth" a query asks for with the "depth" a document covers.
"What is X?" needs an overview, not a troubleshooting guide.
"X error message" needs a specific fix, not a Wikipedia article.
"""

import re
from enum import StrEnum


class QueryIntent(StrEnum):
    OVERVIEW = "overview"
    TUTORIAL = "tutorial"
    TROUBLESHOOT = "troubleshoot"
    REFERENCE = "reference"
    NEWS = "news"
    COMPARISON = "comparison"
    UNKNOWN = "unknown"


# --- Query intent classification (rule-based) ---

_OVERVIEW_RE = re.compile(
    r"^(?:what (?:is|are)|define |meaning of |"
    r"\u3068\u306f|\u3063\u3066\u4f55|\u610f\u5473)",  # とは, って何, 意味
    re.IGNORECASE,
)
_TUTORIAL_RE = re.compile(
    r"^(?:how to |how do |tutorial|guide |"
    r"\u65b9\u6cd5|\u3084\u308a\u65b9|\u4f7f\u3044\u65b9|\u624b\u9806)",
    # 方法, やり方, 使い方, 手順
    re.IGNORECASE,
)
_TROUBLESHOOT_WORDS = frozenset([
    "error", "not working", "fix", "debug", "issue", "bug",
    "failed", "crash", "broken", "traceback", "exception",
    "エラー", "動かない", "修正", "バグ",
])
_REFERENCE_WORDS = frozenset([
    "api", "documentation", "docs", "reference", "spec",
    "specification", "syntax", "manual",
    "リファレンス", "仕様",
])
_NEWS_RE = re.compile(
    r"\b(?:latest|new|202[4-9]|update|release|announce|launch)\b"
    r"|(?:\u6700\u65b0|\u30ea\u30ea\u30fc\u30b9|\u30a2\u30c3\u30d7\u30c7\u30fc\u30c8)",
    # 最新, リリース, アップデート
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r"\bvs\.?\b|\bversus\b|\bcompared? to\b|\b\u6bd4\u8f03\b|\b\u9055\u3044\b",
    # 比較, 違い
    re.IGNORECASE,
)


def classify_query_intent(query: str) -> QueryIntent:
    """Classify query into intent category using rule-based patterns."""
    q = query.strip()
    if not q:
        return QueryIntent.UNKNOWN

    if _OVERVIEW_RE.search(q):
        return QueryIntent.OVERVIEW
    if _TUTORIAL_RE.search(q):
        return QueryIntent.TUTORIAL
    if _COMPARISON_RE.search(q):
        return QueryIntent.COMPARISON

    q_lower = q.lower()
    if any(w in q_lower for w in _TROUBLESHOOT_WORDS):
        return QueryIntent.TROUBLESHOOT
    if any(w in q_lower for w in _REFERENCE_WORDS):
        return QueryIntent.REFERENCE
    if _NEWS_RE.search(q):
        return QueryIntent.NEWS

    return QueryIntent.UNKNOWN


# --- Document type classification (URL + content heuristics) ---

_DOC_TYPE_URL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("reference", re.compile(r"/(?:docs?|api|reference|manual)/", re.I)),
    ("tutorial", re.compile(r"/(?:tutorial|guide|how-to|getting-started)/", re.I)),
    ("news", re.compile(r"/(?:news|blog|press|announce|release)/", re.I)),
    ("forum", re.compile(
        r"(?:stackoverflow|stackexchange|reddit|forum|discuss|community)\.",
        re.I,
    )),
    ("academic", re.compile(r"(?:arxiv\.org|scholar\.google|doi\.org)", re.I)),
    ("official", re.compile(
        r"(?:\.gov(?:\.\w{2})?/|\.edu/|\.ac\.\w{2}/)",
        re.I,
    )),
]


def classify_document_type(url: str) -> str:
    """Classify document type from URL patterns."""
    for doc_type, pattern in _DOC_TYPE_URL_PATTERNS:
        if pattern.search(url):
            return doc_type
    return "general"


# --- Intent ↔ document type affinity ---

_INTENT_AFFINITY: dict[QueryIntent, dict[str, float]] = {
    QueryIntent.OVERVIEW: {
        "reference": 1.0, "academic": 0.9, "official": 0.8,
        "general": 0.6, "news": 0.4, "tutorial": 0.5,
    },
    QueryIntent.TUTORIAL: {
        "tutorial": 1.0, "general": 0.7, "reference": 0.5,
        "forum": 0.6,
    },
    QueryIntent.TROUBLESHOOT: {
        "forum": 0.9, "general": 0.8, "tutorial": 0.7,
        "reference": 0.5,
    },
    QueryIntent.REFERENCE: {
        "reference": 1.0, "official": 0.9, "academic": 0.8,
        "general": 0.5,
    },
    QueryIntent.NEWS: {
        "news": 1.0, "general": 0.6, "official": 0.7,
    },
    QueryIntent.COMPARISON: {
        "general": 0.8, "reference": 0.7, "news": 0.5,
    },
}

_DEFAULT_AFFINITY = 0.5


def compute_scope_match(intent: QueryIntent, doc_type: str) -> float:
    """Score how well a document type matches the query intent."""
    if intent == QueryIntent.UNKNOWN:
        return _DEFAULT_AFFINITY
    affinity = _INTENT_AFFINITY.get(intent, {})
    return affinity.get(doc_type, _DEFAULT_AFFINITY)
