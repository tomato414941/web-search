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
    demote_recruiting: bool = True


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
        domains=("developers.openai.com", "platform.openai.com"),
        preferred_paths=("/api/", "/docs"),
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

_RECRUITING_QUERY_TERMS = frozenset(
    {"job", "jobs", "career", "careers", "hiring", "recruiting", "recruitment"}
)
_RECRUITING_HOST_TERMS = ("talentio.com", "wantedly.com", "breezy.hr")
_RECRUITING_PATH_TERMS = (
    "/careers",
    "/career",
    "/jobs",
    "/job",
    "/hiring",
    "/recruit",
    "/career_page",
)
_RECRUITING_TITLE_TERMS = (
    "career",
    "careers",
    "hiring",
    "job",
    "jobs",
    "recruit",
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

    demote_recruiting = not any(
        term in _RECRUITING_QUERY_TERMS for term in query_text.split()
    )

    match = _match_source(query_text)
    if match is None:
        return SearchRankingPolicy(
            query_class="other",
            demote_recruiting=demote_recruiting,
        )

    source, alias = match
    remainder = query_text[len(alias) :].strip()
    if not remainder:
        return SearchRankingPolicy(
            query_class=source.default_class,
            source=source,
            demote_recruiting=demote_recruiting,
        )

    remainder_terms = tuple(remainder.split())
    if any(term in _OTHER_QUERY_MARKERS for term in remainder_terms):
        return SearchRankingPolicy(
            query_class="other",
            demote_recruiting=demote_recruiting,
        )
    if all(term in _NAVIGATIONAL_SUFFIXES for term in remainder_terms):
        return SearchRankingPolicy(
            query_class=source.default_class,
            source=source,
            demote_recruiting=demote_recruiting,
        )
    return SearchRankingPolicy(
        query_class="reference",
        source=source,
        demote_recruiting=demote_recruiting,
    )


def candidate_window_size(
    k: int,
    page: int,
    policy: SearchRankingPolicy,
    *,
    candidate_limit: int,
) -> int:
    if page != 1:
        return k
    if policy.query_class == "other" or policy.source is None:
        if policy.demote_recruiting:
            return min(candidate_limit, max(k, 20))
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


def _is_recruiting_hit(hit: SearchHit) -> bool:
    parsed = urlparse(hit.url)
    host = parsed.netloc.lower()
    path = parsed.path.lower() or "/"
    title = hit.title.lower()
    if any(
        host == domain or host.endswith(f".{domain}")
        for domain in _RECRUITING_HOST_TERMS
    ):
        return True
    if any(term in path for term in _RECRUITING_PATH_TERMS):
        return True
    return any(term in title for term in _RECRUITING_TITLE_TERMS)


def rerank_hits(
    hits: list[SearchHit], policy: SearchRankingPolicy, *, limit: int
) -> list[SearchHit]:
    if not hits:
        return hits[:limit]

    ranked = hits
    if policy.query_class != "other" and policy.source is not None:
        ranked = sorted(
            ranked,
            key=lambda hit: _canonical_match_score(hit, policy.source),
            reverse=True,
        )
    if policy.demote_recruiting:
        ranked = sorted(ranked, key=_is_recruiting_hit)
    return ranked[:limit]
