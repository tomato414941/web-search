import re
from dataclasses import dataclass
from urllib.parse import urlparse

from web_search_frontend.services.search_query import PreparedSearchQuery
from web_search_search_config.canonical_sources import (
    CanonicalQueryClass,
    CanonicalSourceConfig,
    load_canonical_source_configs,
)
from web_search_kernel.searcher import SearchHit

QueryClass = CanonicalQueryClass

_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_COMPARISON_SPLIT_RE = re.compile(r"\s+(?:vs|versus)\s+")
_NAVIGATIONAL_SUFFIXES = frozenset(
    {"api", "docs", "documentation", "homepage", "official"}
)
_OTHER_QUERY_MARKERS = frozenset({"compare", "comparison", "how", "vs", "what"})
_NEWS_QUERY_MARKERS = frozenset({"news"})
_COMPARISON_CUE_RE = re.compile(r"\b(?:vs\.?|versus|compare|comparison)\b")
_ROOTISH_PATHS = frozenset(
    {"", "/", "/docs", "/docs/", "/learn", "/learn/", "/reference", "/reference/"}
)
_COMPARISON_LOW_SIGNAL_PATH_TERMS = (
    "/pricing",
    "/pricing/",
    "/alternative",
    "/alternatives",
    "/review",
    "/reviews",
    "/category",
    "/categories",
    "/products",
    "/product/",
)
_COMPARISON_LOW_SIGNAL_TITLE_TERMS = (
    "pricing",
    "alternative",
    "alternatives",
    "review",
    "reviews",
)
_INTENT_STOP_TERMS = frozenset({"doc", "docs", "documentation", "homepage", "official"})


@dataclass(frozen=True)
class ComparisonIntent:
    subjects: tuple[str, str]


@dataclass(frozen=True)
class SearchRankingPolicy:
    query_class: QueryClass
    source: CanonicalSourceConfig | None = None
    intent_terms: tuple[str, ...] = ()
    demote_recruiting: bool = True
    restrict_to_source: bool = False
    comparison: ComparisonIntent | None = None


@dataclass(frozen=True)
class RankingSignals:
    page_rank: float
    domain_rank: float
    canonical_source_match: int
    title_intent_match: int
    path_intent_match: int
    comparison_intent_match: int
    is_recruiting_page: bool


@dataclass(frozen=True)
class _RankedHit:
    hit: SearchHit
    signals: RankingSignals
    original_index: int
    normalized_domain: str


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
_CANONICAL_SOURCES = load_canonical_source_configs()


def _normalize_query_text(query: str) -> str:
    return " ".join(_QUERY_TOKEN_RE.findall(query.lower()))


def _query_tokens(query: str) -> tuple[str, ...]:
    return tuple(_QUERY_TOKEN_RE.findall(query.lower()))


def _extract_comparison_intent(query_text: str) -> ComparisonIntent | None:
    parts = _COMPARISON_SPLIT_RE.split(query_text, maxsplit=1)
    if len(parts) != 2:
        return None

    left = parts[0].strip()
    right = parts[1].strip()
    if not left or not right or left == right:
        return None

    return ComparisonIntent(subjects=(left, right))


def _match_source(query_text: str) -> tuple[CanonicalSourceConfig, str] | None:
    best_match: tuple[CanonicalSourceConfig, str] | None = None
    for source in _CANONICAL_SOURCES:
        for alias in source.aliases:
            if query_text != alias and not query_text.startswith(f"{alias} "):
                continue
            if best_match is None or len(alias) > len(best_match[1]):
                best_match = (source, alias)
    return best_match


def _source_identity_terms(source: CanonicalSourceConfig) -> frozenset[str]:
    alias_tokens = [_query_tokens(alias) for alias in source.aliases]
    first_terms = {tokens[0] for tokens in alias_tokens if tokens}
    if len(first_terms) == 1:
        return frozenset(first_terms)
    return frozenset()


def _intent_terms_for_source_query(
    query_text: str, source: CanonicalSourceConfig
) -> tuple[str, ...]:
    identity_terms = _source_identity_terms(source)
    terms: list[str] = []
    for term in _query_tokens(query_text):
        if term in identity_terms or term in _INTENT_STOP_TERMS:
            continue
        terms.append(term)
    return tuple(terms)


def _intent_terms_for_comparison(comparison: ComparisonIntent) -> tuple[str, ...]:
    terms: list[str] = []
    for subject in comparison.subjects:
        terms.extend(_query_tokens(subject))
    return tuple(terms)


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
    comparison = _extract_comparison_intent(query_text)

    match = _match_source(query_text)
    if match is None:
        return SearchRankingPolicy(
            query_class="comparison" if comparison is not None else "other",
            intent_terms=(
                _intent_terms_for_comparison(comparison)
                if comparison is not None
                else ()
            ),
            demote_recruiting=demote_recruiting,
            comparison=comparison,
        )

    source, alias = match
    intent_terms = _intent_terms_for_source_query(query_text, source)
    remainder = query_text[len(alias) :].strip()
    if not remainder:
        return SearchRankingPolicy(
            query_class=source.default_class,
            source=source,
            intent_terms=intent_terms,
            demote_recruiting=demote_recruiting,
            restrict_to_source=source.restrict_to_source,
            comparison=comparison,
        )

    remainder_terms = tuple(remainder.split())
    if (
        all(term in _NEWS_QUERY_MARKERS for term in remainder_terms)
        and source.news_paths
    ):
        return SearchRankingPolicy(
            query_class="news",
            source=source,
            intent_terms=intent_terms,
            demote_recruiting=demote_recruiting,
            restrict_to_source=source.restrict_to_source,
            comparison=comparison,
        )
    if any(term in _OTHER_QUERY_MARKERS for term in remainder_terms):
        return SearchRankingPolicy(
            query_class="comparison" if comparison is not None else "other",
            intent_terms=(
                _intent_terms_for_comparison(comparison)
                if comparison is not None
                else intent_terms
            ),
            demote_recruiting=demote_recruiting,
            comparison=comparison,
        )
    if all(term in _NAVIGATIONAL_SUFFIXES for term in remainder_terms):
        return SearchRankingPolicy(
            query_class=source.default_class,
            source=source,
            intent_terms=intent_terms,
            demote_recruiting=demote_recruiting,
            restrict_to_source=source.restrict_to_source,
            comparison=comparison,
        )
    return SearchRankingPolicy(
        query_class="reference",
        source=source,
        intent_terms=intent_terms,
        demote_recruiting=demote_recruiting,
        restrict_to_source=source.restrict_to_source,
        comparison=comparison,
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
    if policy.query_class == "comparison":
        return min(candidate_limit, max(k, 100))
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


def _canonical_source_match_score(
    hit: SearchHit, source: CanonicalSourceConfig, query_class: QueryClass
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


def _normalize_host(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _term_matches_token(term: str, token: str) -> bool:
    return token == term or token.startswith(term) or term.startswith(token)


def _intent_match_score(terms: tuple[str, ...], text: str) -> int:
    if not terms:
        return 0
    tokens = _query_tokens(text)
    return sum(
        1 for term in terms if any(_term_matches_token(term, token) for token in tokens)
    )


def ranking_signals_for_hit(
    hit: SearchHit, policy: SearchRankingPolicy
) -> RankingSignals:
    canonical_source_match = 0
    if policy.query_class != "other" and policy.source is not None:
        canonical_source_match = _canonical_source_match_score(
            hit, policy.source, policy.query_class
        )

    parsed = urlparse(hit.url)
    path = parsed.path or "/"
    title_intent_match = _intent_match_score(policy.intent_terms, hit.title)
    path_intent_match = _intent_match_score(policy.intent_terms, path)

    comparison_intent_match = 0
    if policy.query_class == "comparison" and policy.comparison is not None:
        comparison_intent_match = _comparison_intent_match_score(hit, policy.comparison)

    return RankingSignals(
        page_rank=hit.page_rank or 0.0,
        domain_rank=hit.domain_rank or 0.0,
        canonical_source_match=canonical_source_match,
        title_intent_match=title_intent_match,
        path_intent_match=path_intent_match,
        comparison_intent_match=comparison_intent_match,
        is_recruiting_page=policy.demote_recruiting and _is_recruiting_hit(hit),
    )


def _is_shallow_root_like_path(path: str) -> bool:
    if path in _ROOTISH_PATHS:
        return True
    segments = [segment for segment in path.split("/") if segment]
    return len(segments) <= 1


def _comparison_text(hit: SearchHit) -> str:
    return f"{hit.title} {hit.url} {hit.content}".lower()


def _comparison_intent_match_score(hit: SearchHit, comparison: ComparisonIntent) -> int:
    text = _comparison_text(hit)
    title = hit.title.lower()
    path = (urlparse(hit.url).path or "/").lower()
    subject_matches = tuple(subject in text for subject in comparison.subjects)
    title_matches = tuple(subject in title for subject in comparison.subjects)
    path_matches = tuple(subject in path for subject in comparison.subjects)
    cue_in_text = _COMPARISON_CUE_RE.search(text) is not None
    cue_in_title = _COMPARISON_CUE_RE.search(title) is not None
    cue_in_path = _COMPARISON_CUE_RE.search(path) is not None
    low_signal_title = any(term in title for term in _COMPARISON_LOW_SIGNAL_TITLE_TERMS)
    low_signal_path = any(term in path for term in _COMPARISON_LOW_SIGNAL_PATH_TERMS)

    score = 0
    if all(title_matches):
        score += 6
    elif all(path_matches):
        score += 5
    elif all(subject_matches):
        score += 4

    if cue_in_title or cue_in_path:
        score += 4
    elif cue_in_text:
        score += 3

    if sum(subject_matches) == 1 and _is_shallow_root_like_path(path):
        score -= 4
    if not all(title_matches) and not all(path_matches) and cue_in_text:
        score -= 2
    if low_signal_title or low_signal_path:
        score -= 3
    if (low_signal_title or low_signal_path) and not (cue_in_title or cue_in_path):
        score -= 2

    return score


def _promote_domain_diversity_for_comparison(
    hits: list[_RankedHit],
) -> list[_RankedHit]:
    seen_domains: set[str] = set()
    unique_domain_hits: list[_RankedHit] = []
    duplicate_domain_hits: list[_RankedHit] = []

    for hit in hits:
        if hit.normalized_domain in seen_domains:
            duplicate_domain_hits.append(hit)
            continue
        seen_domains.add(hit.normalized_domain)
        unique_domain_hits.append(hit)

    return unique_domain_hits + duplicate_domain_hits


def rerank_hits(
    hits: list[SearchHit], policy: SearchRankingPolicy, *, limit: int
) -> list[SearchHit]:
    if not hits:
        return hits[:limit]

    ranked = [
        _RankedHit(
            hit=hit,
            signals=ranking_signals_for_hit(hit, policy),
            original_index=index,
            normalized_domain=_normalize_host(urlparse(hit.url).netloc.lower()),
        )
        for index, hit in enumerate(hits)
    ]

    if policy.query_class == "comparison" and policy.comparison is not None:
        ranked = sorted(
            ranked,
            key=lambda item: (
                not item.signals.is_recruiting_page,
                item.signals.comparison_intent_match,
                item.signals.title_intent_match,
                item.signals.path_intent_match,
                item.signals.page_rank,
                item.signals.domain_rank,
                -item.original_index,
            ),
            reverse=True,
        )
        return [item.hit for item in _promote_domain_diversity_for_comparison(ranked)][
            :limit
        ]

    if policy.query_class in {"navigational", "reference", "news"}:
        ranked = sorted(
            ranked,
            key=lambda item: (
                not item.signals.is_recruiting_page,
                item.signals.canonical_source_match,
                item.signals.title_intent_match,
                item.signals.path_intent_match,
                item.signals.page_rank,
                item.signals.domain_rank,
                -item.original_index,
            ),
            reverse=True,
        )
        return [item.hit for item in ranked[:limit]]

    ranked = sorted(
        ranked,
        key=lambda item: (not item.signals.is_recruiting_page, -item.original_index),
        reverse=True,
    )
    return [item.hit for item in ranked[:limit]]
