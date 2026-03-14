from frontend.services.search_query import prepare_search_query
from frontend.services.search_ranking_policy import (
    candidate_window_size,
    canonical_paths_for_policy,
    classify_query_policy,
    rerank_hits,
)
from shared.search_kernel.searcher import SearchHit


def test_classify_query_policy_marks_google_as_navigational():
    policy = classify_query_policy("Google", prepare_search_query("Google"))

    assert policy.query_class == "navigational"
    assert policy.source is not None
    assert policy.source.key == "google"


def test_classify_query_policy_marks_postgresql_jsonb_as_reference():
    policy = classify_query_policy(
        "PostgreSQL jsonb",
        prepare_search_query("PostgreSQL jsonb"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "postgresql"


def test_classify_query_policy_maps_openai_api_to_developers_docs():
    policy = classify_query_policy(
        "OpenAI API",
        prepare_search_query("OpenAI API"),
    )

    assert policy.query_class == "navigational"
    assert policy.source is not None
    assert policy.source.key == "openai"
    assert "developers.openai.com" in policy.source.domains
    assert "/api/" in policy.source.preferred_paths


def test_classify_query_policy_maps_openai_news_to_news_policy():
    policy = classify_query_policy(
        "OpenAI news",
        prepare_search_query("OpenAI news"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "openai"


def test_classify_query_policy_maps_github_docs_to_docs_source():
    policy = classify_query_policy(
        "GitHub docs",
        prepare_search_query("GitHub docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "github_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_react_documentation_to_react_docs_source():
    policy = classify_query_policy(
        "React documentation",
        prepare_search_query("React documentation"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "react_docs"


def test_classify_query_policy_maps_python_asyncio_to_specific_docs_source():
    policy = classify_query_policy(
        "Python asyncio docs",
        prepare_search_query("Python asyncio docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "python_asyncio"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_python_release_to_news_source():
    policy = classify_query_policy(
        "Python 3.13 release",
        prepare_search_query("Python 3.13 release"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "python_313_release"
    assert policy.restrict_to_source is True


def test_candidate_window_size_expands_first_page_for_canonical_queries():
    policy = classify_query_policy("GitHub", prepare_search_query("GitHub"))

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 100


def test_candidate_window_size_expands_first_page_for_news_queries():
    policy = classify_query_policy("OpenAI news", prepare_search_query("OpenAI news"))

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 100


def test_canonical_paths_for_news_policy_uses_news_paths():
    policy = classify_query_policy("OpenAI news", prepare_search_query("OpenAI news"))

    paths = canonical_paths_for_policy(policy)

    assert paths == ("/blog", "/api/docs/changelog")


def test_candidate_window_size_keeps_reference_queries_smaller():
    policy = classify_query_policy(
        "PostgreSQL jsonb",
        prepare_search_query("PostgreSQL jsonb"),
    )

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 20


def test_candidate_window_size_expands_broad_docs_queries():
    policy = classify_query_policy(
        "GitHub docs",
        prepare_search_query("GitHub docs"),
    )

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 100


def test_candidate_window_size_expands_other_queries_for_recruiting_demotion():
    policy = classify_query_policy(
        "site reliability engineering",
        prepare_search_query("site reliability engineering"),
    )

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 20


def test_rerank_hits_promotes_canonical_homepage():
    policy = classify_query_policy("Google", prepare_search_query("Google"))
    hits = [
        SearchHit(
            url="https://vr.google.com/intl/ja_jp/cardboard/",
            title="Cardboard",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://google.com/",
            title="Google",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://cardboard.google.com/",
            title="Cardboard",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://google.com/",
        "https://vr.google.com/intl/ja_jp/cardboard/",
        "https://cardboard.google.com/",
    ]


def test_rerank_hits_demotes_recruiting_pages_for_non_recruiting_queries():
    policy = classify_query_policy(
        "site reliability engineering",
        prepare_search_query("site reliability engineering"),
    )
    hits = [
        SearchHit(
            url="https://open.talentio.com/r/1/c/smsc/pages/58450",
            title="Site Reliability Engineering",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://www.usenix.org/conference/srecon18asia/presentation/purgason",
            title="The Evolution of Site Reliability Engineering",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://training.linuxfoundation.org/devops-site-reliability/",
            title="DevOps & Site Reliability",
            content="x",
            score=8.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://www.usenix.org/conference/srecon18asia/presentation/purgason",
        "https://training.linuxfoundation.org/devops-site-reliability/",
        "https://open.talentio.com/r/1/c/smsc/pages/58450",
    ]


def test_rerank_hits_promotes_openai_news_sources():
    policy = classify_query_policy("OpenAI news", prepare_search_query("OpenAI news"))
    hits = [
        SearchHit(
            url="https://community.openai.com/t/openai-dev-day-2023-announcement/472706",
            title="OpenAI dev-day 2023: announcement!",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://developers.openai.com/blog",
            title="Blog",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://developers.openai.com/api/docs/changelog",
            title="Changelog | OpenAI API",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://developers.openai.com/blog",
        "https://developers.openai.com/api/docs/changelog",
        "https://community.openai.com/t/openai-dev-day-2023-announcement/472706",
    ]


def test_rerank_hits_promotes_github_docs_paths():
    policy = classify_query_policy("GitHub docs", prepare_search_query("GitHub docs"))
    hits = [
        SearchHit(
            url="https://docs.renovatebot.com/",
            title="Renovate docs",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.github.com/en",
            title="GitHub Docs",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://docs.github.com/en/contributing/writing-for-github-docs",
            title="Writing for GitHub Docs",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.github.com/en",
        "https://docs.github.com/en/contributing/writing-for-github-docs",
        "https://docs.renovatebot.com/",
    ]


def test_rerank_hits_promotes_python_docs_contents():
    policy = classify_query_policy(
        "Python documentation",
        prepare_search_query("Python documentation"),
    )
    hits = [
        SearchHit(
            url="https://docs.python.org/3/using/windows.html",
            title="Using Python on Windows",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.python.org/3/library/py_compile.html",
            title="py_compile",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://docs.python.org/3.15/contents.html",
            title="Python Documentation Contents",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.python.org/3.15/contents.html",
        "https://docs.python.org/3/using/windows.html",
        "https://docs.python.org/3/library/py_compile.html",
    ]


def test_rerank_hits_promotes_python_release_notes():
    policy = classify_query_policy(
        "Python 3.13 release",
        prepare_search_query("Python 3.13 release"),
    )
    hits = [
        SearchHit(
            url="https://docs.python.org/3/using/windows.html",
            title="Using Python on Windows",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.python.org/3.13/whatsnew/3.13.html",
            title="What's New in Python 3.13",
            content="x",
            score=4.0,
        ),
        SearchHit(
            url="https://docs.python.org/3/library/py_compile.html",
            title="py_compile",
            content="x",
            score=9.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.python.org/3.13/whatsnew/3.13.html",
        "https://docs.python.org/3/using/windows.html",
        "https://docs.python.org/3/library/py_compile.html",
    ]


def test_rerank_hits_prefers_react_reference_over_blog_and_versions():
    policy = classify_query_policy("React docs", prepare_search_query("React docs"))
    hits = [
        SearchHit(
            url="https://react.dev/versions",
            title="React Versions",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://react.dev/blog",
            title="React Blog",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://react.dev/reference/react",
            title="React Reference Overview",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://react.dev/reference/react",
        "https://react.dev/versions",
        "https://react.dev/blog",
    ]
