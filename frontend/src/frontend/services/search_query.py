from dataclasses import dataclass

from shared.search_kernel.analyzer import analyzer
from shared.search_kernel.searcher import SearchResult, parse_query


@dataclass(frozen=True)
class PreparedSearchQuery:
    parsed: object
    tokens: str
    positive_query: str
    exact_phrases: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    exclude_phrases: tuple[str, ...]
    tokenized_exact_phrases: tuple[str, ...]
    tokenized_exclude_terms: tuple[str, ...]
    tokenized_exclude_phrases: tuple[str, ...]

    @property
    def embedding_query(self) -> str:
        return self.positive_query or self.tokens

    @property
    def has_opensearch_terms(self) -> bool:
        return bool(self.tokens.strip() or self.tokenized_exact_phrases)


@dataclass(frozen=True)
class OpenSearchExecutionPlan:
    use_diversity: bool
    fetch_size: int
    fetch_offset: int


def _tokenize_search_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        tokenized for value in values if (tokenized := analyzer.tokenize(value).strip())
    )


def prepare_search_query(q: str) -> PreparedSearchQuery:
    parsed = parse_query(q)
    tokens = analyzer.tokenize(parsed.text) if parsed.text else ""
    exact_phrases = tuple(phrase for phrase in parsed.exact_phrases if phrase)
    exclude_terms = tuple(term for term in parsed.exclude_terms if term)
    exclude_phrases = tuple(phrase for phrase in parsed.exclude_phrases if phrase)
    return PreparedSearchQuery(
        parsed=parsed,
        tokens=tokens,
        positive_query=parsed.positive_text(),
        exact_phrases=exact_phrases,
        exclude_terms=exclude_terms,
        exclude_phrases=exclude_phrases,
        tokenized_exact_phrases=_tokenize_search_values(exact_phrases),
        tokenized_exclude_terms=_tokenize_search_values(exclude_terms),
        tokenized_exclude_phrases=_tokenize_search_values(exclude_phrases),
    )


def build_snippet_terms(q: str) -> list[str]:
    search_query = prepare_search_query(q)
    snippet_query = search_query.embedding_query or q
    analyzed_q = analyzer.tokenize(snippet_query)
    if analyzed_q.strip():
        return analyzed_q.split()
    return [snippet_query]


def build_opensearch_plan(
    search_query: PreparedSearchQuery,
    k: int,
    page: int,
    *,
    overscan: int,
    candidate_limit: int,
) -> OpenSearchExecutionPlan:
    use_diversity = not search_query.parsed.site_filter
    if use_diversity:
        return OpenSearchExecutionPlan(
            use_diversity=True,
            fetch_size=min(page * k * overscan, candidate_limit),
            fetch_offset=0,
        )
    return OpenSearchExecutionPlan(
        use_diversity=False,
        fetch_size=k,
        fetch_offset=(page - 1) * k,
    )


def empty_search_result(q: str, k: int) -> SearchResult:
    return SearchResult(query=q, total=0, hits=[], page=1, per_page=k, last_page=1)
