"""Crawl profile classification and priority assignment."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from web_search_search_config.canonical_sources import load_canonical_source_configs

_CANONICAL_SOURCES = load_canonical_source_configs()
_NEWS_PATH_TERMS = (
    "/news",
    "/blog",
    "/blogs",
    "/releases",
    "/release",
    "/release-notes",
    "/changelog",
    "/whatsnew",
    "/announcements",
)
_RELEASE_NOTES_PATH_TERMS = (
    "/releases",
    "/release",
    "/release-notes",
    "/changelog",
    "/whatsnew",
)
_BLOG_PATH_TERMS = ("/blog", "/blogs")
_NEWS_ROOT_PATH_TERMS = ("/news", "/announcements")
_ROOTISH_PATHS = frozenset(("", "/"))


@dataclass(frozen=True)
class CrawlPolicy:
    name: str
    budget_tier: str
    budget_weight: int
    priority_bucket: int
    priority_score_boost: float
    base_recrawl_interval_sec: int
    canonical_recrawl_interval_sec: int | None
    failure_retry_delay_sec: int
    max_outlinks: int
    host_concurrency_limit: int
    host_min_interval_sec: float
    retry_budget: int
    discovery_depth_limit: int


@dataclass(frozen=True)
class CrawlPolicyAssignment:
    crawl_profile: str
    canonical_source: str | None
    priority_bucket: int
    priority_score: float
    initial_next_fetch_delay_sec: int


POLICIES: dict[str, CrawlPolicy] = {
    "manual_now": CrawlPolicy(
        name="manual_now",
        budget_tier="operator",
        budget_weight=0,
        priority_bucket=0,
        priority_score_boost=200.0,
        base_recrawl_interval_sec=0,
        canonical_recrawl_interval_sec=0,
        failure_retry_delay_sec=15 * 60,
        max_outlinks=50,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=1,
    ),
    "release_notes": CrawlPolicy(
        name="release_notes",
        budget_tier="hot",
        budget_weight=4,
        priority_bucket=1,
        priority_score_boost=120.0,
        base_recrawl_interval_sec=4 * 3600,
        canonical_recrawl_interval_sec=1 * 3600,
        failure_retry_delay_sec=30 * 60,
        max_outlinks=40,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=2,
    ),
    "news_root": CrawlPolicy(
        name="news_root",
        budget_tier="hot",
        budget_weight=4,
        priority_bucket=1,
        priority_score_boost=110.0,
        base_recrawl_interval_sec=4 * 3600,
        canonical_recrawl_interval_sec=2 * 3600,
        failure_retry_delay_sec=30 * 60,
        max_outlinks=40,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=2,
    ),
    "blog_root": CrawlPolicy(
        name="blog_root",
        budget_tier="hot",
        budget_weight=4,
        priority_bucket=1,
        priority_score_boost=90.0,
        base_recrawl_interval_sec=8 * 3600,
        canonical_recrawl_interval_sec=4 * 3600,
        failure_retry_delay_sec=60 * 60,
        max_outlinks=40,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=2,
    ),
    "canonical_docs": CrawlPolicy(
        name="canonical_docs",
        budget_tier="reference",
        budget_weight=3,
        priority_bucket=1,
        priority_score_boost=100.0,
        base_recrawl_interval_sec=7 * 24 * 3600,
        canonical_recrawl_interval_sec=5 * 24 * 3600,
        failure_retry_delay_sec=6 * 3600,
        max_outlinks=50,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=3,
    ),
    "article": CrawlPolicy(
        name="article",
        budget_tier="bulk",
        budget_weight=1,
        priority_bucket=2,
        priority_score_boost=40.0,
        base_recrawl_interval_sec=30 * 24 * 3600,
        canonical_recrawl_interval_sec=14 * 24 * 3600,
        failure_retry_delay_sec=24 * 3600,
        max_outlinks=20,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=2,
    ),
    "generic": CrawlPolicy(
        name="generic",
        budget_tier="bulk",
        budget_weight=1,
        priority_bucket=3,
        priority_score_boost=0.0,
        base_recrawl_interval_sec=30 * 24 * 3600,
        canonical_recrawl_interval_sec=None,
        failure_retry_delay_sec=3 * 24 * 3600,
        max_outlinks=20,
        host_concurrency_limit=2,
        host_min_interval_sec=1.0,
        retry_budget=3,
        discovery_depth_limit=2,
    ),
}


def _match_canonical_source(url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    for source in _CANONICAL_SOURCES:
        if not any(
            host == domain or host == f"www.{domain}" or host.endswith(f".{domain}")
            for domain in source.domains
        ):
            continue
        if source.news_paths and any(
            path == prefix or path.startswith(prefix.rstrip("/") + "/")
            for prefix in source.news_paths
        ):
            return source.key, "news"
        if source.preferred_paths and any(
            path == prefix or path.startswith(prefix.rstrip("/") + "/")
            for prefix in source.preferred_paths
        ):
            return source.key, "docs"
        if source.default_class == "news":
            return source.key, "news"
        return source.key, "docs"
    return None, None


def _classify_url_profile(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    canonical_source, canonical_kind = _match_canonical_source(url)
    segments = tuple(segment for segment in path.strip("/").split("/") if segment)

    if any(term in path for term in _RELEASE_NOTES_PATH_TERMS):
        return "release_notes", canonical_source
    if canonical_kind == "news":
        if _is_blog_root_path(path, segments):
            return "blog_root", canonical_source
        if _is_news_root_path(path, segments):
            return "news_root", canonical_source
        return "article", canonical_source
    if canonical_kind == "docs":
        return "canonical_docs", canonical_source
    if any(term in path for term in _NEWS_PATH_TERMS):
        if _is_blog_root_path(path, segments):
            return "blog_root", canonical_source
        if _is_news_root_path(path, segments):
            return "news_root", canonical_source
        return "article", canonical_source
    return "generic", canonical_source


def _is_exact_or_child_path(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _is_blog_root_path(path: str, segments: tuple[str, ...]) -> bool:
    return any(
        _is_exact_or_child_path(path, prefix) and len(segments) <= 2
        for prefix in _BLOG_PATH_TERMS
    )


def _is_news_root_path(path: str, segments: tuple[str, ...]) -> bool:
    return any(
        _is_exact_or_child_path(path, prefix) and len(segments) <= 1
        for prefix in _NEWS_ROOT_PATH_TERMS
    )


def assign_crawl_policy(
    url: str,
    *,
    discovered_via: str = "outlink",
) -> CrawlPolicyAssignment:
    if discovered_via == "manual":
        policy = POLICIES["manual_now"]
        return CrawlPolicyAssignment(
            crawl_profile=policy.name,
            canonical_source=None,
            priority_bucket=policy.priority_bucket,
            priority_score=policy.priority_score_boost,
            initial_next_fetch_delay_sec=0,
        )

    profile_name, canonical_source = _classify_url_profile(url)
    policy = POLICIES[profile_name]
    priority_bucket = policy.priority_bucket
    priority_score = policy.priority_score_boost

    return CrawlPolicyAssignment(
        crawl_profile=policy.name,
        canonical_source=canonical_source,
        priority_bucket=priority_bucket,
        priority_score=priority_score,
        initial_next_fetch_delay_sec=0,
    )


def compute_success_recrawl_delay(
    crawl_profile: str,
    *,
    canonical_source: str | None = None,
) -> int:
    policy = POLICIES.get(crawl_profile, POLICIES["generic"])
    candidates = [policy.base_recrawl_interval_sec]
    if canonical_source and policy.canonical_recrawl_interval_sec is not None:
        candidates.append(policy.canonical_recrawl_interval_sec)
    return min(candidates)


def compute_failure_retry_delay(
    crawl_profile: str,
    *,
    fail_streak: int = 0,
) -> int:
    policy = POLICIES.get(crawl_profile, POLICIES["generic"])
    multiplier = 2 ** min(max(fail_streak, 0), 3)
    return policy.failure_retry_delay_sec * multiplier
