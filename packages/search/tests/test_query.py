from web_search_engine.query import prepare_search_query


def test_question_text_is_preserved():
    query = prepare_search_query("What is BM25")
    assert query.positive_query == "What is BM25"
    assert query.tokens == "what is bm25"


def test_operators_are_separate_from_semantic_text():
    query = prepare_search_query(
        'Python "type hints" site:docs.python.org -snake -"old version"'
    )
    assert query.positive_query == "Python type hints"
    assert query.parsed.site_filter == "docs.python.org"
    assert query.tokenized_exact_phrases == ("type hints",)
    assert query.tokenized_exclude_terms == ("snake",)
    assert query.tokenized_exclude_phrases == ("old version",)
