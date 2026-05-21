"""Core search evaluation logic."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
import re
import urllib.parse

from web_search_search_config.canonical_sources import CanonicalEvalCase, EvalJudgment


@dataclass(frozen=True)
class CaseEvaluation:
    query: str
    query_type: str
    status: str
    reason: str
    metrics: dict[str, float | int | None]
    total: int
    mode: str
    expected: str
    notes: str
    top_hits: list[dict[str, object]]


@dataclass(frozen=True)
class EvaluationReport:
    generated_at: str
    base_url: str
    limit: int
    counts: dict[str, int]
    aggregate_metrics: dict[str, dict[str, float]]
    cases: list[CaseEvaluation]
    errors: int

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "base_url": self.base_url,
            "limit": self.limit,
            "counts": self.counts,
            "aggregate_metrics": self.aggregate_metrics,
            "cases": [asdict(case) for case in self.cases],
            "errors": self.errors,
        }


def extract_domain(text: str, known_domains: list[str]) -> str | None:
    match = re.search(r"`([^`]+)`", text)
    if match:
        return match.group(1).lower()

    lowered = text.lower()
    for domain in sorted(known_domains, key=len, reverse=True):
        if domain in lowered:
            return domain
    return None


def normalize_url_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower()


def normalize_url_path(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.path or "/"


def normalize_exact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    scheme = parsed.scheme.lower()
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def hit_text(hit: dict) -> str:
    return " ".join(
        str(hit.get(field, "")) for field in ("title", "url", "snip_plain", "snip")
    ).lower()


def hit_title(hit: dict) -> str:
    return str(hit.get("title", "")).lower()


def domain_matches(
    expected_domain: str, actual_domain: str, *, allow_subdomain: bool
) -> bool:
    if actual_domain == expected_domain or actual_domain == f"www.{expected_domain}":
        return True
    if allow_subdomain and actual_domain.endswith(f".{expected_domain}"):
        return True
    return False


def hit_matches_rule(
    hit: dict,
    *,
    required_terms: tuple[str, ...] = (),
    any_of_terms: tuple[str, ...] = (),
    required_title_terms: tuple[str, ...] = (),
    required_domains: tuple[str, ...] = (),
    excluded_domains: tuple[str, ...] = (),
    required_paths: tuple[str, ...] = (),
    required_path_terms: tuple[str, ...] = (),
) -> bool:
    text = hit_text(hit)
    title = hit_title(hit)
    url = str(hit.get("url", ""))
    domain = normalize_url_domain(url)
    path = normalize_url_path(url)

    if required_domains and not any(
        domain_matches(expected, domain, allow_subdomain=True)
        for expected in required_domains
    ):
        return False

    if excluded_domains and any(
        domain_matches(excluded, domain, allow_subdomain=True)
        for excluded in excluded_domains
    ):
        return False

    if required_paths and path not in required_paths:
        return False

    if required_path_terms and not any(term in path for term in required_path_terms):
        return False

    if required_title_terms and not all(term in title for term in required_title_terms):
        return False

    if required_terms and not all(term in text for term in required_terms):
        return False

    if any_of_terms and not any(term in text for term in any_of_terms):
        return False

    return True


def judgment_matches_hit(judgment: EvalJudgment, hit: dict) -> bool:
    url = str(hit.get("url", ""))
    normalized_url = normalize_exact_url(url) if url else ""
    domain = normalize_url_domain(url)
    path = normalize_url_path(url)
    title = hit_title(hit)

    if judgment.url and normalized_url != normalize_exact_url(judgment.url):
        return False
    if judgment.domain and not domain_matches(
        judgment.domain.lower(), domain, allow_subdomain=True
    ):
        return False
    if judgment.path_prefix and not path.startswith(judgment.path_prefix):
        return False
    if judgment.title_terms and not all(term in title for term in judgment.title_terms):
        return False
    return True


def _explicit_rule_payload(
    case: CanonicalEvalCase, keyword_rules: dict[str, dict]
) -> dict | None:
    if case.has_explicit_rule:
        payload: dict[str, object] = {
            "required_terms": list(case.required_terms),
            "required_domains": list(case.required_domains),
            "minimum_domain_matches": case.minimum_domain_matches,
            "any_of_terms": list(case.any_of_terms),
            "required_title_terms": list(case.required_title_terms),
            "required_paths": list(case.required_paths),
            "required_path_terms": list(case.required_path_terms),
            "excluded_domains": list(case.excluded_domains),
            "pass_reason": case.pass_reason or "",
            "fail_reason": case.fail_reason or "",
        }
        if case.max_match_rank is not None:
            payload["max_match_rank"] = case.max_match_rank
        return payload
    return keyword_rules.get(case.query_key)


def hit_relevance(
    case: CanonicalEvalCase,
    hit: dict,
    *,
    keyword_rules: dict[str, dict],
    known_domains: list[str],
) -> int:
    matched_judgments = [
        judgment.relevance
        for judgment in case.judgments
        if judgment_matches_hit(judgment, hit)
    ]
    if matched_judgments:
        return max(matched_judgments)

    rule = _explicit_rule_payload(case, keyword_rules)
    if rule and hit_matches_rule(
        hit,
        required_terms=tuple(rule.get("required_terms") or ()),
        any_of_terms=tuple(rule.get("any_of_terms") or ()),
        required_title_terms=tuple(rule.get("required_title_terms") or ()),
        required_domains=tuple(rule.get("required_domains") or ()),
        excluded_domains=tuple(rule.get("excluded_domains") or ()),
        required_paths=tuple(rule.get("required_paths") or ()),
        required_path_terms=tuple(rule.get("required_path_terms") or ()),
    ):
        return 3

    expected_domain = extract_domain(case.expected, known_domains)
    if not expected_domain:
        return 0

    domain = normalize_url_domain(str(hit.get("url", "")))
    path = normalize_url_path(str(hit.get("url", "")))

    if case.query_type == "navigational":
        expects_homepage = "homepage" in case.notes.lower()
        allow_subdomain = not expects_homepage
        if not domain_matches(expected_domain, domain, allow_subdomain=allow_subdomain):
            return 0
        if expects_homepage and path not in {"", "/"}:
            return 2
        return 3

    if "reference" in case.query_type:
        if domain_matches(expected_domain, domain, allow_subdomain=True):
            return 3

    if case.query_type == "news":
        if domain_matches(expected_domain, domain, allow_subdomain=True):
            return 3

    return 0


def _dcg(relevances: list[int], k: int) -> float:
    total = 0.0
    for index, relevance in enumerate(relevances[:k], start=1):
        if relevance <= 0:
            continue
        total += (2**relevance - 1) / math.log2(index + 1)
    return total


def compute_case_metrics(
    case: CanonicalEvalCase,
    payload: dict,
    *,
    keyword_rules: dict[str, dict],
    known_domains: list[str],
) -> tuple[dict[str, float | int | None], list[int]]:
    hits = payload.get("hits") or []
    relevances = [
        hit_relevance(
            case, hit, keyword_rules=keyword_rules, known_domains=known_domains
        )
        for hit in hits
    ]
    first_relevant_rank = next(
        (index for index, relevance in enumerate(relevances, start=1) if relevance > 0),
        None,
    )
    exact_url_judgments = [
        judgment
        for judgment in case.judgments
        if judgment.url
        and not judgment.domain
        and not judgment.path_prefix
        and not judgment.title_terms
    ]
    if exact_url_judgments and len(exact_url_judgments) == len(case.judgments):
        ideal_relevances = sorted(
            [judgment.relevance for judgment in exact_url_judgments],
            reverse=True,
        )
    else:
        ideal_relevances = sorted(relevances, reverse=True)

    ndcg_at_3 = 0.0
    ndcg_at_10 = 0.0
    idcg_at_3 = _dcg(ideal_relevances, 3)
    idcg_at_10 = _dcg(ideal_relevances, 10)
    if idcg_at_3 > 0:
        ndcg_at_3 = _dcg(relevances, 3) / idcg_at_3
    if idcg_at_10 > 0:
        ndcg_at_10 = _dcg(relevances, 10) / idcg_at_10

    metrics: dict[str, float | int | None] = {
        "hit_at_1": 1.0 if any(relevance > 0 for relevance in relevances[:1]) else 0.0,
        "hit_at_3": 1.0 if any(relevance > 0 for relevance in relevances[:3]) else 0.0,
        "mrr": 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
        "ndcg_at_3": ndcg_at_3,
        "ndcg_at_10": ndcg_at_10,
        "first_relevant_rank": first_relevant_rank,
    }
    return metrics, relevances


def classify_case(
    case: CanonicalEvalCase,
    payload: dict,
    *,
    keyword_rules: dict[str, dict],
    known_domains: list[str],
) -> tuple[str, str]:
    hits = payload.get("hits") or []
    total = int(payload.get("total") or 0)
    expected_domain = extract_domain(case.expected, known_domains)
    top_urls = [hit.get("url", "") for hit in hits[:3]]
    top_domains = [normalize_url_domain(str(url)) for url in top_urls]
    top_paths = [normalize_url_path(str(url)) for url in top_urls]
    keyword_rule = _explicit_rule_payload(case, keyword_rules)

    if total == 0:
        return "fail", "0 hits"

    if keyword_rule:
        max_match_rank = int(keyword_rule.get("max_match_rank") or 3)
        rule_hits = hits[:max_match_rank]
        required_domains = tuple(keyword_rule.get("required_domains") or ())
        minimum_domain_matches = int(keyword_rule.get("minimum_domain_matches") or 1)
        required_title_terms = tuple(keyword_rule.get("required_title_terms") or ())
        required_paths = tuple(keyword_rule.get("required_paths") or ())
        required_path_terms = tuple(keyword_rule.get("required_path_terms") or ())
        excluded_domains = tuple(keyword_rule.get("excluded_domains") or ())
        if required_domains:
            matches = sum(
                hit_matches_rule(
                    hit,
                    required_domains=required_domains,
                    excluded_domains=excluded_domains,
                    required_paths=required_paths,
                    required_path_terms=required_path_terms,
                    required_title_terms=required_title_terms,
                )
                for hit in rule_hits
            )
            if matches >= minimum_domain_matches:
                return "pass", str(keyword_rule["pass_reason"])
            return "fail", str(keyword_rule["fail_reason"])

        required_terms = tuple(keyword_rule.get("required_terms") or ())
        if required_terms:
            any_of_terms = tuple(keyword_rule.get("any_of_terms") or ())
            if any(
                hit_matches_rule(
                    hit,
                    required_terms=required_terms,
                    any_of_terms=any_of_terms,
                    required_title_terms=required_title_terms,
                    required_paths=required_paths,
                    required_path_terms=required_path_terms,
                )
                for hit in rule_hits
            ):
                return "pass", str(keyword_rule["pass_reason"])
            return "fail", str(keyword_rule["fail_reason"])

    if case.query_type == "navigational":
        if not expected_domain:
            return "fail", "no expected domain parsed"
        expects_homepage = "homepage" in case.notes.lower()
        allow_subdomain = not expects_homepage
        for idx, (domain, path) in enumerate(zip(top_domains, top_paths), start=1):
            if not domain_matches(
                expected_domain, domain, allow_subdomain=allow_subdomain
            ):
                continue
            if expects_homepage and path not in {"", "/"}:
                continue
            if idx <= 3:
                return "pass", "official destination is in top 3"
        return "fail", "official destination missing from top 3"

    if "reference" in case.query_type:
        if not expected_domain:
            return "fail", "no expected domain parsed"
        if any(
            domain_matches(expected_domain, domain, allow_subdomain=True)
            for domain in top_domains
        ):
            return "pass", "canonical docs are in top 3"
        return "fail", "canonical docs missing from top 3"

    if case.query_type == "news" and expected_domain:
        if any(expected_domain in domain for domain in top_domains):
            return "pass", "expected source is in top 3"
        return "fail", "expected source missing from top 3"

    if case.query_type in {"overview", "troubleshooting", "comparison", "news"}:
        return "fail", "no automatic pass rule matched"

    return "fail", "unsupported query type"


def aggregate_metrics(cases: list[CaseEvaluation]) -> dict[str, dict[str, float]]:
    def _avg(values: list[float]) -> float:
        return 0.0 if not values else sum(values) / len(values)

    def _group_rows(rows: list[CaseEvaluation]) -> dict[str, float]:
        if not rows:
            return {}
        metric_names = ("hit_at_1", "hit_at_3", "mrr", "ndcg_at_3", "ndcg_at_10")
        return {
            metric_name: _avg(
                [
                    float(case.metrics[metric_name])
                    for case in rows
                    if case.metrics.get(metric_name) is not None
                ]
            )
            for metric_name in metric_names
        }

    by_type: dict[str, list[CaseEvaluation]] = {}
    for case in cases:
        by_type.setdefault(case.query_type, []).append(case)

    aggregate = {"all": _group_rows(cases)}
    aggregate.update(
        {name: _group_rows(rows) for name, rows in sorted(by_type.items())}
    )
    return aggregate


def build_report(
    *,
    base_url: str,
    limit: int,
    counts: dict[str, int],
    cases: list[CaseEvaluation],
    errors: int,
) -> EvaluationReport:
    return EvaluationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        base_url=base_url,
        limit=limit,
        counts=counts,
        aggregate_metrics=aggregate_metrics(cases),
        cases=cases,
        errors=errors,
    )
