import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from frontend.services.search_query import PreparedSearchQuery
from shared.search_kernel.searcher import SearchHit

QueryClass = Literal["navigational", "reference", "other"]

_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NAVIGATIONAL_SUFFIXES = frozenset(
    {"api", "docs", "documentation", "homepage", "official"}
)
_OTHER_QUERY_MARKERS = frozenset({"compare", "comparison", "how", "news", "vs", "what"})


@dataclass(frozen=True)
class CanonicalSource:
    key: str
    aliases: tuple[str, ...]
    domains: tuple[str, ...]
    preferred_paths: tuple[str, ...] = ()
    default_class: QueryClass = "reference"


@dataclass(frozen=True)
class SearchRankingPolicy:
    query_class: QueryClass
    source: CanonicalSource | None = None


_CANONICAL_SOURCES = (
    CanonicalSource(
        key="google",
        aliases=("google",),
        domains=("google.com",),
        preferred_paths=("/",),
        default_class="navigational",
    ),
    CanonicalSource(
        key="github",
        aliases=("github",),
        domains=("github.com",),
        preferred_paths=("/",),
        default_class="navigational",
    ),
    CanonicalSource(
        key="fastapi",
        aliases=("fastapi",),
        domains=("fastapi.tiangolo.com",),
        default_class="navigational",
    ),
    CanonicalSource(
        key="openai",
        aliases=("openai api", "openai docs", "openai"),
        domains=("platform.openai.com",),
        preferred_paths=("/docs",),
        default_class="navigational",
    ),
    CanonicalSource(
        key="python",
        aliases=("python documentation", "python docs", "python"),
        domains=("docs.python.org",),
        default_class="reference",
    ),
    CanonicalSource(
        key="postgresql",
        aliases=("postgresql", "postgres"),
        domains=("postgresql.org",),
        preferred_paths=("/docs/",),
        default_class="reference",
    ),
)


def _normalize_query_text(query: str) -> str:
    return " ".join(_QUERY_TOKEN_RE.findall(query.lower()))


def _match_source(query_text: str) -> tuple[CanonicalSource, str] | None:
    best_match: tuple[CanonicalSource, str] | None = None
    for source in _CANONICAL_SOURCES:
        for alias in source.aliases:
            if query_text != alias and not query_text.startswith(f"{alias} "):
                continue
            if best_match is None or len(alias) > len(best_match[1]):
                best_match = (source, alias)
    return best_match


def classify_query_policy(
    q: str, search_query: PreparedSearchQuery
) -> SearchRankingPolicy:
    if search_query.parsed.site_filter:
        return SearchRankingPolicy(query_class="other")

    query_text = _normalize_query_text(search_query.positive_query or q)
    if not query_text:
        return SearchRankingPolicy(query_class="other")

    match = _match_source(query_text)
    if match is None:
        return SearchRankingPolicy(query_class="other")

    source, alias = match
    remainder = query_text[len(alias) :].strip()
    if not remainder:
        return SearchRankingPolicy(query_class=source.default_class, source=source)

    remainder_terms = tuple(remainder.split())
    if any(term in _OTHER_QUERY_MARKERS for term in remainder_terms):
        return SearchRankingPolicy(query_class="other")
    if all(term in _NAVIGATIONAL_SUFFIXES for term in remainder_terms):
        return SearchRankingPolicy(query_class=source.default_class, source=source)
    return SearchRankingPolicy(query_class="reference", source=source)


def candidate_window_size(
    k: int,
    page: int,
    policy: SearchRankingPolicy,
    *,
    candidate_limit: int,
) -> int:
    if page != 1 or policy.query_class == "other" or policy.source is None:
        return k
    if policy.query_class == "navigational":
        return min(candidate_limit, max(k, 100))
    return min(candidate_limit, max(k, 20))


def _domain_matches(candidate_domains: tuple[str, ...], host: str) -> bool:
    return any(
        host == domain or host == f"www.{domain}" for domain in candidate_domains
    )


def _canonical_match_score(hit: SearchHit, source: CanonicalSource) -> int:
    parsed = urlparse(hit.url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    if not _domain_matches(source.domains, host):
        return 0
    if any(
        path in {"", "/"} if prefix == "/" else path.startswith(prefix)
        for prefix in source.preferred_paths
    ):
        return 2
    return 1


def rerank_hits(
    hits: list[SearchHit], policy: SearchRankingPolicy, *, limit: int
) -> list[SearchHit]:
    if policy.query_class == "other" or policy.source is None or not hits:
        return hits[:limit]
    ranked = sorted(
        hits,
        key=lambda hit: _canonical_match_score(hit, policy.source),
        reverse=True,
    )
    return ranked[:limit]
