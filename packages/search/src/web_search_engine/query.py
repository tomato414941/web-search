from dataclasses import dataclass

from web_search_kernel.analyzer import analyzer
from web_search_kernel.searcher import ParsedQuery, SearchResult, parse_query


@dataclass(frozen=True)
class PreparedSearchQuery:
    parsed: ParsedQuery
    tokens: str
    positive_query: str
    exact_phrases: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    exclude_phrases: tuple[str, ...]
    tokenized_exact_phrases: tuple[str, ...]
    tokenized_exclude_terms: tuple[str, ...]
    tokenized_exclude_phrases: tuple[str, ...]

    @property
    def has_opensearch_terms(self) -> bool:
        return bool(self.tokens.strip() or self.tokenized_exact_phrases)


def _tokenize_search_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        tokenized for value in values if (tokenized := analyzer.tokenize(value).strip())
    )


def prepare_search_query(q: str) -> PreparedSearchQuery:
    parsed = parse_query(q)
    normalized_text = parsed.text.strip()
    tokens = analyzer.tokenize(normalized_text) if normalized_text else ""
    exact_phrases = tuple(phrase for phrase in parsed.exact_phrases if phrase)
    exclude_terms = tuple(term for term in parsed.exclude_terms if term)
    exclude_phrases = tuple(phrase for phrase in parsed.exclude_phrases if phrase)
    positive_query = " ".join(
        part for part in (normalized_text, *exact_phrases) if part
    )
    return PreparedSearchQuery(
        parsed=parsed,
        tokens=tokens,
        positive_query=positive_query,
        exact_phrases=exact_phrases,
        exclude_terms=exclude_terms,
        exclude_phrases=exclude_phrases,
        tokenized_exact_phrases=_tokenize_search_values(exact_phrases),
        tokenized_exclude_terms=_tokenize_search_values(exclude_terms),
        tokenized_exclude_phrases=_tokenize_search_values(exclude_phrases),
    )


def build_snippet_terms(q: str) -> list[str]:
    search_query = prepare_search_query(q)
    snippet_query = search_query.positive_query or q
    analyzed_q = analyzer.tokenize(snippet_query)
    if analyzed_q.strip():
        return analyzed_q.split()
    return [snippet_query]


def empty_search_result(q: str, k: int) -> SearchResult:
    return SearchResult(query=q, total=0, hits=[], page=1, per_page=k, last_page=1)
