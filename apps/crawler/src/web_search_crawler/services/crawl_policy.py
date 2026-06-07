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
_OPERATOR_PRIORITY_BUCKET = 0
_OPERATOR_PRIORITY_SCORE = 200.0


@dataclass(frozen=True)
class CrawlPolicy:
    name: str
    priority_bucket: int
    priority_score_boost: float
    base_recrawl_interval_sec: int
    failure_retry_delay_sec: int
    host_min_interval_sec: float


@dataclass(frozen=True)
class CrawlPolicyAssignment:
    crawl_profile: str
    priority_bucket: int
    priority_score: float
    initial_next_fetch_delay_sec: int


POLICIES: dict[str, CrawlPolicy] = {
    "release_notes": CrawlPolicy(
        name="release_notes",
        priority_bucket=1,
        priority_score_boost=120.0,
        base_recrawl_interval_sec=4 * 3600,
        failure_retry_delay_sec=30 * 60,
        host_min_interval_sec=1.0,
    ),
    "news_root": CrawlPolicy(
        name="news_root",
        priority_bucket=1,
        priority_score_boost=110.0,
        base_recrawl_interval_sec=4 * 3600,
        failure_retry_delay_sec=30 * 60,
        host_min_interval_sec=1.0,
    ),
    "blog_root": CrawlPolicy(
        name="blog_root",
        priority_bucket=1,
        priority_score_boost=90.0,
        base_recrawl_interval_sec=8 * 3600,
        failure_retry_delay_sec=60 * 60,
        host_min_interval_sec=1.0,
    ),
    "canonical_docs": CrawlPolicy(
        name="canonical_docs",
        priority_bucket=1,
        priority_score_boost=100.0,
        base_recrawl_interval_sec=7 * 24 * 3600,
        failure_retry_delay_sec=6 * 3600,
        host_min_interval_sec=1.0,
    ),
    "article": CrawlPolicy(
        name="article",
        priority_bucket=2,
        priority_score_boost=40.0,
        base_recrawl_interval_sec=30 * 24 * 3600,
        failure_retry_delay_sec=24 * 3600,
        host_min_interval_sec=1.0,
    ),
    "generic": CrawlPolicy(
        name="generic",
        priority_bucket=3,
        priority_score_boost=0.0,
        base_recrawl_interval_sec=30 * 24 * 3600,
        failure_retry_delay_sec=3 * 24 * 3600,
        host_min_interval_sec=1.0,
    ),
}


def _match_configured_source_kind(url: str) -> str | None:
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
            return "news"
        if source.preferred_paths and any(
            path == prefix or path.startswith(prefix.rstrip("/") + "/")
            for prefix in source.preferred_paths
        ):
            return "docs"
        if source.default_class == "news":
            return "news"
        return "docs"
    return None


def _classify_url_profile(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    configured_source_kind = _match_configured_source_kind(url)
    segments = tuple(segment for segment in path.strip("/").split("/") if segment)

    if any(term in path for term in _RELEASE_NOTES_PATH_TERMS):
        return "release_notes"
    if configured_source_kind == "news":
        if _is_blog_root_path(path, segments):
            return "blog_root"
        if _is_news_root_path(path, segments):
            return "news_root"
        return "article"
    if configured_source_kind == "docs":
        return "canonical_docs"
    if any(term in path for term in _NEWS_PATH_TERMS):
        if _is_blog_root_path(path, segments):
            return "blog_root"
        if _is_news_root_path(path, segments):
            return "news_root"
        return "article"
    return "generic"


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
    admission_intent: str = "normal",
) -> CrawlPolicyAssignment:
    profile_name = _classify_url_profile(url)
    policy = POLICIES[profile_name]

    if admission_intent == "operator_priority":
        return CrawlPolicyAssignment(
            crawl_profile=policy.name,
            priority_bucket=_OPERATOR_PRIORITY_BUCKET,
            priority_score=_OPERATOR_PRIORITY_SCORE,
            initial_next_fetch_delay_sec=0,
        )

    priority_bucket = policy.priority_bucket
    priority_score = policy.priority_score_boost

    return CrawlPolicyAssignment(
        crawl_profile=policy.name,
        priority_bucket=priority_bucket,
        priority_score=priority_score,
        initial_next_fetch_delay_sec=0,
    )


def compute_success_recrawl_delay(crawl_profile: str) -> int:
    policy = POLICIES.get(crawl_profile, POLICIES["generic"])
    return policy.base_recrawl_interval_sec


def compute_failure_retry_delay(
    crawl_profile: str,
    *,
    fail_streak: int = 0,
) -> int:
    policy = POLICIES.get(crawl_profile, POLICIES["generic"])
    multiplier = 2 ** min(max(fail_streak, 0), 3)
    return policy.failure_retry_delay_sec * multiplier
