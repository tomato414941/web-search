"""URL-derived crawl scheduling parameters."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

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
_REFERENCE_PATH_TERMS = ("/docs", "/doc", "/documentation", "/reference", "/api")
_ROOTISH_PATHS = frozenset(("", "/"))
_OPERATOR_PRIORITY_BUCKET = 0
_OPERATOR_PRIORITY_SCORE = 200.0


@dataclass(frozen=True)
class CrawlSchedulingParameters:
    priority_bucket: int
    priority_score_boost: float
    base_recrawl_interval_sec: int
    failure_retry_delay_sec: int


@dataclass(frozen=True)
class CrawlAdmissionSchedule:
    priority_bucket: int
    priority_score: float
    initial_next_fetch_delay_sec: int


SCHEDULING_PARAMETERS: dict[str, CrawlSchedulingParameters] = {
    "release_notes": CrawlSchedulingParameters(
        priority_bucket=1,
        priority_score_boost=120.0,
        base_recrawl_interval_sec=4 * 3600,
        failure_retry_delay_sec=30 * 60,
    ),
    "news_root": CrawlSchedulingParameters(
        priority_bucket=1,
        priority_score_boost=110.0,
        base_recrawl_interval_sec=4 * 3600,
        failure_retry_delay_sec=30 * 60,
    ),
    "blog_root": CrawlSchedulingParameters(
        priority_bucket=1,
        priority_score_boost=90.0,
        base_recrawl_interval_sec=8 * 3600,
        failure_retry_delay_sec=60 * 60,
    ),
    "reference_docs": CrawlSchedulingParameters(
        priority_bucket=1,
        priority_score_boost=100.0,
        base_recrawl_interval_sec=7 * 24 * 3600,
        failure_retry_delay_sec=6 * 3600,
    ),
    "article": CrawlSchedulingParameters(
        priority_bucket=2,
        priority_score_boost=40.0,
        base_recrawl_interval_sec=30 * 24 * 3600,
        failure_retry_delay_sec=24 * 3600,
    ),
    "generic": CrawlSchedulingParameters(
        priority_bucket=3,
        priority_score_boost=0.0,
        base_recrawl_interval_sec=30 * 24 * 3600,
        failure_retry_delay_sec=3 * 24 * 3600,
    ),
}


def _classify_url_schedule_key(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    segments = tuple(segment for segment in path.strip("/").split("/") if segment)

    if any(term in path for term in _RELEASE_NOTES_PATH_TERMS):
        return "release_notes"
    if any(term in path for term in _NEWS_PATH_TERMS):
        if _is_blog_root_path(path, segments):
            return "blog_root"
        if _is_news_root_path(path, segments):
            return "news_root"
        return "article"
    if any(_is_exact_or_child_path(path, prefix) for prefix in _REFERENCE_PATH_TERMS):
        return "reference_docs"
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


def compute_admission_schedule(
    url: str,
    *,
    admission_intent: str = "normal",
) -> CrawlAdmissionSchedule:
    schedule_key = _classify_url_schedule_key(url)
    parameters = SCHEDULING_PARAMETERS[schedule_key]

    if admission_intent == "operator_priority":
        return CrawlAdmissionSchedule(
            priority_bucket=_OPERATOR_PRIORITY_BUCKET,
            priority_score=_OPERATOR_PRIORITY_SCORE,
            initial_next_fetch_delay_sec=0,
        )

    priority_bucket = parameters.priority_bucket
    priority_score = parameters.priority_score_boost

    return CrawlAdmissionSchedule(
        priority_bucket=priority_bucket,
        priority_score=priority_score,
        initial_next_fetch_delay_sec=0,
    )


def get_scheduling_parameters_for_url(url: str) -> CrawlSchedulingParameters:
    schedule_key = _classify_url_schedule_key(url)
    return SCHEDULING_PARAMETERS[schedule_key]


def compute_success_recrawl_delay_for_url(url: str) -> int:
    parameters = get_scheduling_parameters_for_url(url)
    return parameters.base_recrawl_interval_sec


def compute_failure_retry_delay_for_url(
    url: str,
    *,
    fail_streak: int = 0,
) -> int:
    parameters = get_scheduling_parameters_for_url(url)
    multiplier = 2 ** min(max(fail_streak, 0), 3)
    return parameters.failure_retry_delay_sec * multiplier
