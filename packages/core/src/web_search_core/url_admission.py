from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from web_search_core.utils import MAX_URL_LENGTH

_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
}


@dataclass(frozen=True)
class DomainAdmissionRule:
    domains: tuple[str, ...]
    allow_path_prefixes: tuple[str, ...] = ()
    reject_path_prefixes: tuple[str, ...] = ()
    reject_path_contains: tuple[str, ...] = ()
    reject_query_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdmissionDecision:
    action: str
    normalized_url: str | None
    reason_code: str | None
    scope_key: str | None = None


class URLAdmissionPolicy:
    def __init__(
        self,
        *,
        drop_query_params: tuple[str, ...],
        reject_extensions: frozenset[str],
        reject_path_prefixes: tuple[str, ...],
        reject_path_contains: tuple[str, ...],
        reject_query_params: frozenset[str],
        domain_rules: tuple[DomainAdmissionRule, ...],
    ):
        self._drop_query_params = frozenset(
            param.lower() for param in drop_query_params
        )
        self._reject_extensions = frozenset(ext.lower() for ext in reject_extensions)
        self._reject_path_prefixes = tuple(
            prefix.lower() for prefix in reject_path_prefixes
        )
        self._reject_path_contains = tuple(
            token.lower() for token in reject_path_contains
        )
        self._reject_query_params = frozenset(
            param.lower() for param in reject_query_params
        )
        self._domain_rules = domain_rules

    def evaluate(self, url: str) -> AdmissionDecision:
        normalized_url = self._normalize_url(url)
        if normalized_url is None:
            return AdmissionDecision(
                action="reject",
                normalized_url=None,
                reason_code="invalid_url",
            )

        parsed = urlsplit(normalized_url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or "/"
        lowered_path = path.lower()
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_keys = frozenset(key.lower() for key, _ in query_pairs)

        dot_idx = lowered_path.rfind(".")
        if dot_idx != -1 and lowered_path[dot_idx:] in self._reject_extensions:
            return AdmissionDecision("reject", normalized_url, "filtered_extension")

        if any(
            lowered_path == prefix or lowered_path.startswith(prefix.rstrip("/") + "/")
            for prefix in self._reject_path_prefixes
        ):
            return AdmissionDecision("reject", normalized_url, "filtered_path_prefix")

        if any(token in lowered_path for token in self._reject_path_contains):
            return AdmissionDecision("reject", normalized_url, "filtered_path_contains")

        if query_keys & self._reject_query_params:
            return AdmissionDecision("reject", normalized_url, "filtered_query_param")

        for rule in self._domain_rules:
            if not self._matches_domain_rule(host, rule):
                continue
            if rule.allow_path_prefixes and not any(
                lowered_path == prefix
                or lowered_path.startswith(prefix.rstrip("/") + "/")
                for prefix in rule.allow_path_prefixes
            ):
                return AdmissionDecision(
                    "reject",
                    normalized_url,
                    "domain_scope_denied",
                    scope_key=rule.domains[0],
                )
            if any(
                lowered_path == prefix
                or lowered_path.startswith(prefix.rstrip("/") + "/")
                for prefix in rule.reject_path_prefixes
            ):
                return AdmissionDecision(
                    "reject",
                    normalized_url,
                    "domain_path_prefix_denied",
                    scope_key=rule.domains[0],
                )
            if any(token in lowered_path for token in rule.reject_path_contains):
                return AdmissionDecision(
                    "reject",
                    normalized_url,
                    "domain_path_contains_denied",
                    scope_key=rule.domains[0],
                )
            if query_keys & frozenset(rule.reject_query_params):
                return AdmissionDecision(
                    "reject",
                    normalized_url,
                    "domain_query_param_denied",
                    scope_key=rule.domains[0],
                )

        return AdmissionDecision("allow", normalized_url, None)

    def _normalize_url(self, url: str) -> str | None:
        if not url:
            return None
        try:
            parts = urlsplit(url)
        except ValueError:
            return None
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"}:
            return None
        host = (parts.hostname or "").lower()
        if not host:
            return None
        try:
            port = parts.port
        except ValueError:
            return None
        netloc = host
        if port and _DEFAULT_PORTS.get(scheme) != port:
            netloc = f"{host}:{port}"
        path = parts.path or ""
        query_pairs = sorted(
            (
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if key.lower() not in self._drop_query_params
            ),
            key=lambda item: (item[0], item[1]),
        )
        normalized = urlunsplit(
            (
                scheme,
                netloc,
                path,
                urlencode(query_pairs, doseq=True),
                "",
            )
        )
        if len(normalized) > MAX_URL_LENGTH:
            return None
        return normalized

    @staticmethod
    def _matches_domain_rule(host: str, rule: DomainAdmissionRule) -> bool:
        for domain in rule.domains:
            if host == domain or host.endswith(f".{domain}"):
                return True
        return False


def load_url_admission_policy(path: str | Path) -> URLAdmissionPolicy:
    p = Path(path)
    if not p.exists():
        return URLAdmissionPolicy(
            drop_query_params=(),
            reject_extensions=frozenset(),
            reject_path_prefixes=(),
            reject_path_contains=(),
            reject_query_params=frozenset(),
            domain_rules=(),
        )

    raw = yaml.safe_load(p.read_text()) or {}
    domain_rules = tuple(
        DomainAdmissionRule(
            domains=tuple((entry.get("domains") or [])),
            allow_path_prefixes=tuple(
                prefix.lower() for prefix in entry.get("allow_path_prefixes") or []
            ),
            reject_path_prefixes=tuple(
                prefix.lower() for prefix in entry.get("reject_path_prefixes") or []
            ),
            reject_path_contains=tuple(
                token.lower() for token in entry.get("reject_path_contains") or []
            ),
            reject_query_params=tuple(
                key.lower() for key in entry.get("reject_query_params") or []
            ),
        )
        for entry in raw.get("domain_rules") or []
    )
    return URLAdmissionPolicy(
        drop_query_params=tuple(raw.get("drop_query_params") or []),
        reject_extensions=frozenset(raw.get("reject_extensions") or []),
        reject_path_prefixes=tuple(raw.get("reject_path_prefixes") or []),
        reject_path_contains=tuple(raw.get("reject_path_contains") or []),
        reject_query_params=frozenset(raw.get("reject_query_params") or []),
        domain_rules=domain_rules,
    )
