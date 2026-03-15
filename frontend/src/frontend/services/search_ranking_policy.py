import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from frontend.services.search_query import PreparedSearchQuery
from shared.search_kernel.searcher import SearchHit

QueryClass = Literal["navigational", "reference", "news", "other"]

_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NAVIGATIONAL_SUFFIXES = frozenset(
    {"api", "docs", "documentation", "homepage", "official"}
)
_OTHER_QUERY_MARKERS = frozenset({"compare", "comparison", "how", "vs", "what"})
_NEWS_QUERY_MARKERS = frozenset({"news"})


@dataclass(frozen=True)
class CanonicalSource:
    key: str
    aliases: tuple[str, ...]
    domains: tuple[str, ...]
    preferred_paths: tuple[str, ...] = ()
    news_paths: tuple[str, ...] = ()
    default_class: QueryClass = "reference"
    candidate_window: int = 20
    retrieval_query: str | None = None


@dataclass(frozen=True)
class SearchRankingPolicy:
    query_class: QueryClass
    source: CanonicalSource | None = None
    demote_recruiting: bool = True
    restrict_to_source: bool = False


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
        candidate_window=100,
    ),
    CanonicalSource(
        key="github_docs",
        aliases=("github docs",),
        domains=("docs.github.com",),
        preferred_paths=("/", "/en", "/ja"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="github docs",
    ),
    CanonicalSource(
        key="github_actions_docs",
        aliases=("github actions docs",),
        domains=("docs.github.com",),
        preferred_paths=("/en/actions", "/actions"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="github actions",
    ),
    CanonicalSource(
        key="github_rest_api_docs",
        aliases=("github rest api docs",),
        domains=("docs.github.com",),
        preferred_paths=("/en/rest", "/rest"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="github rest api",
    ),
    CanonicalSource(
        key="fastapi",
        aliases=("fastapi",),
        domains=("fastapi.tiangolo.com",),
        default_class="navigational",
        candidate_window=100,
    ),
    CanonicalSource(
        key="openai",
        aliases=("openai api", "openai docs", "openai"),
        domains=("developers.openai.com", "platform.openai.com"),
        preferred_paths=("/api/", "/docs"),
        news_paths=("/blog", "/api/docs/changelog"),
        default_class="navigational",
    ),
    CanonicalSource(
        key="python",
        aliases=("python",),
        domains=("docs.python.org",),
        default_class="reference",
    ),
    CanonicalSource(
        key="python_docs",
        aliases=("python documentation", "python docs"),
        domains=("docs.python.org",),
        preferred_paths=(
            "/3.15/contents",
            "/3.14/contents",
            "/3.13/contents",
            "/3.12/contents",
            "/3/contents",
            "/contents",
        ),
        default_class="reference",
        candidate_window=100,
        retrieval_query="python documentation",
    ),
    CanonicalSource(
        key="python_asyncio",
        aliases=("python asyncio docs", "python asyncio"),
        domains=("docs.python.org",),
        preferred_paths=("/3/library/asyncio", "/library/asyncio"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="asyncio",
    ),
    CanonicalSource(
        key="python_dataclasses",
        aliases=("python dataclasses",),
        domains=("docs.python.org",),
        preferred_paths=("/3/library/dataclasses", "/library/dataclasses"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="dataclasses",
    ),
    CanonicalSource(
        key="python_313_release",
        aliases=("python 3 13 release",),
        domains=("docs.python.org",),
        news_paths=("/3.13/whatsnew/3.13", "/whatsnew/3.13"),
        default_class="news",
        candidate_window=100,
        retrieval_query="python 3.13 release",
    ),
    CanonicalSource(
        key="react_docs",
        aliases=("react docs", "react documentation"),
        domains=("react.dev",),
        preferred_paths=(
            "/",
            "/learn",
            "/learn/",
            "/reference",
            "/reference/",
            "/reference/react",
            "/reference/react/",
        ),
        default_class="reference",
        candidate_window=100,
        retrieval_query="react reference overview",
    ),
    CanonicalSource(
        key="go_docs",
        aliases=("go documentation", "go docs", "golang documentation"),
        domains=("go.dev",),
        preferred_paths=("/doc", "/doc/"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="go documentation",
    ),
    CanonicalSource(
        key="kubernetes_docs",
        aliases=("kubernetes docs", "kubernetes documentation"),
        domains=("kubernetes.io",),
        preferred_paths=("/docs", "/docs/", "/docs/home", "/docs/home/"),
        default_class="reference",
        candidate_window=100,
        retrieval_query="kubernetes documentation",
    ),
    CanonicalSource(
        key="typescript_docs",
        aliases=("typescript docs", "typescript documentation"),
        domains=("www.typescriptlang.org", "typescriptlang.org"),
        preferred_paths=(
            "/docs",
            "/docs/",
            "/docs/handbook",
            "/docs/handbook/",
            "/docs/handbook/intro",
        ),
        default_class="reference",
        candidate_window=100,
        retrieval_query="typescript handbook documentation",
    ),
    CanonicalSource(
        key="postgresql",
        aliases=("postgresql", "postgres"),
        domains=("postgresql.org",),
        preferred_paths=("/docs/",),
        default_class="reference",
        candidate_window=20,
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
_SOURCE_RESTRICT_KEYS = frozenset(
    {
        "github_docs",
        "github_actions_docs",
        "github_rest_api_docs",
        "python_docs",
        "python_asyncio",
        "python_dataclasses",
        "python_313_release",
        "react_docs",
        "go_docs",
        "kubernetes_docs",
        "typescript_docs",
    }
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
            restrict_to_source=source.key in _SOURCE_RESTRICT_KEYS,
        )

    remainder_terms = tuple(remainder.split())
    if (
        all(term in _NEWS_QUERY_MARKERS for term in remainder_terms)
        and source.news_paths
    ):
        return SearchRankingPolicy(
            query_class="news",
            source=source,
            demote_recruiting=demote_recruiting,
            restrict_to_source=source.key in _SOURCE_RESTRICT_KEYS,
        )
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
            restrict_to_source=source.key in _SOURCE_RESTRICT_KEYS,
        )
    return SearchRankingPolicy(
        query_class="reference",
        source=source,
        demote_recruiting=demote_recruiting,
        restrict_to_source=source.key in _SOURCE_RESTRICT_KEYS,
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
    source_window = max(k, policy.source.candidate_window)
    if policy.query_class == "navigational":
        return min(candidate_limit, max(source_window, 100))
    if policy.query_class == "news":
        return min(candidate_limit, max(source_window, 100))
    return min(candidate_limit, max(source_window, 20))


def canonical_paths_for_policy(policy: SearchRankingPolicy) -> tuple[str, ...]:
    if policy.source is None:
        return ()
    if policy.query_class == "news":
        return policy.source.news_paths
    return policy.source.preferred_paths


def _domain_matches(candidate_domains: tuple[str, ...], host: str) -> bool:
    return any(
        host == domain or host == f"www.{domain}" for domain in candidate_domains
    )


def _canonical_match_score(
    hit: SearchHit, source: CanonicalSource, query_class: QueryClass
) -> int:
    parsed = urlparse(hit.url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    if not _domain_matches(source.domains, host):
        return 0
    preferred_paths = (
        source.news_paths if query_class == "news" else source.preferred_paths
    )
    if any(path == preferred_path for preferred_path in preferred_paths):
        return 3
    if any(
        path in {"", "/"} if prefix == "/" else path.startswith(prefix)
        for prefix in preferred_paths
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
            key=lambda hit: _canonical_match_score(
                hit, policy.source, policy.query_class
            ),
            reverse=True,
        )
    if policy.demote_recruiting:
        ranked = sorted(ranked, key=_is_recruiting_hit)
    return ranked[:limit]
