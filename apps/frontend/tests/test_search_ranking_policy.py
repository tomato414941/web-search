from web_search_frontend.services.search_query import prepare_search_query
from web_search_frontend.services.search_ranking_policy import (
    candidate_window_size,
    canonical_paths_for_policy,
    classify_query_policy,
    ranking_signals_for_hit,
    rerank_hits,
)
from web_search_kernel.searcher import SearchHit


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
    assert policy.source.key == "openai_api"
    assert "developers.openai.com" in policy.source.domains
    assert "/api/" in policy.source.preferred_paths


def test_classify_query_policy_maps_openai_news_to_news_policy():
    policy = classify_query_policy(
        "OpenAI news",
        prepare_search_query("OpenAI news"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "openai_news"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_openai_announcements_to_news_policy():
    policy = classify_query_policy(
        "OpenAI announcements",
        prepare_search_query("OpenAI announcements"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "openai_announcements"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_github_docs_to_docs_source():
    policy = classify_query_policy(
        "GitHub docs",
        prepare_search_query("GitHub docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "github_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_docker_docs_to_docs_source():
    policy = classify_query_policy(
        "Docker docs",
        prepare_search_query("Docker docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "docker_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_pytest_fixture_to_docs_source():
    policy = classify_query_policy(
        "pytest fixture",
        prepare_search_query("pytest fixture"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "pytest_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_react_documentation_to_react_docs_source():
    policy = classify_query_policy(
        "React documentation",
        prepare_search_query("React documentation"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "react_docs"


def test_classify_query_policy_maps_mdn_fetch_api_to_specific_source():
    policy = classify_query_policy(
        "MDN fetch API",
        prepare_search_query("MDN fetch API"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "mdn_fetch_api"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_go_documentation_to_go_docs_source():
    policy = classify_query_policy(
        "Go documentation",
        prepare_search_query("Go documentation"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "go_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_kubernetes_docs_to_specific_docs_source():
    policy = classify_query_policy(
        "Kubernetes docs",
        prepare_search_query("Kubernetes docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "kubernetes_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_typescript_docs_to_specific_docs_source():
    policy = classify_query_policy(
        "TypeScript docs",
        prepare_search_query("TypeScript docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "typescript_docs"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_python_asyncio_to_specific_docs_source():
    policy = classify_query_policy(
        "Python asyncio docs",
        prepare_search_query("Python asyncio docs"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "python_asyncio"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_sre_query_to_canonical_source():
    policy = classify_query_policy(
        "site reliability engineering",
        prepare_search_query("site reliability engineering"),
    )

    assert policy.query_class == "reference"
    assert policy.source is not None
    assert policy.source.key == "site_reliability_engineering"
    assert policy.restrict_to_source is False


def test_classify_query_policy_maps_python_release_to_news_source():
    policy = classify_query_policy(
        "Python 3.13 release",
        prepare_search_query("Python 3.13 release"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "python_313_release"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_python_release_notes_to_news_source():
    policy = classify_query_policy(
        "Python release notes",
        prepare_search_query("Python release notes"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "python_release_notes"
    assert policy.restrict_to_source is True


def test_classify_query_policy_maps_django_release_notes_to_news_source():
    policy = classify_query_policy(
        "Django release notes",
        prepare_search_query("Django release notes"),
    )

    assert policy.query_class == "news"
    assert policy.source is not None
    assert policy.source.key == "django_release_notes"
    assert policy.restrict_to_source is True


def test_classify_query_policy_detects_comparison_intent():
    policy = classify_query_policy(
        "FastAPI vs Django",
        prepare_search_query("FastAPI vs Django"),
    )

    assert policy.query_class == "comparison"
    assert policy.comparison is not None
    assert policy.comparison.subjects == ("fastapi", "django")


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

    assert paths == ("/news", "/news/", "/index", "/index/")


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


def test_candidate_window_size_expands_comparison_queries():
    policy = classify_query_policy(
        "OpenSearch vs Elasticsearch",
        prepare_search_query("OpenSearch vs Elasticsearch"),
    )

    size = candidate_window_size(3, 1, policy, candidate_limit=200)

    assert size == 100


def test_ranking_signals_include_link_and_canonical_matches():
    policy = classify_query_policy("GitHub docs", prepare_search_query("GitHub docs"))
    hit = SearchHit(
        url="https://docs.github.com/en",
        title="GitHub Docs",
        content="x",
        score=10.0,
        page_rank=0.2,
        domain_rank=0.4,
    )

    signals = ranking_signals_for_hit(hit, policy)

    assert signals.page_rank == 0.2
    assert signals.domain_rank == 0.4
    assert signals.canonical_source_match == 3
    assert signals.title_intent_match == 0
    assert signals.path_intent_match == 0


def test_ranking_signals_include_title_and_path_intent_matches():
    policy = classify_query_policy(
        "Docker compose file reference",
        prepare_search_query("Docker compose file reference"),
    )
    hit = SearchHit(
        url="https://docs.docker.com/compose/compose-file/",
        title="Compose file reference | Docker Docs",
        content="x",
        score=10.0,
    )

    signals = ranking_signals_for_hit(hit, policy)

    assert policy.intent_terms == ("compose", "file", "reference")
    assert signals.title_intent_match == 3
    assert signals.path_intent_match == 2


def test_ranking_signals_include_comparison_match():
    policy = classify_query_policy(
        "OpenSearch vs Elasticsearch",
        prepare_search_query("OpenSearch vs Elasticsearch"),
    )
    hit = SearchHit(
        url="https://example.com/opensearch-vs-elasticsearch",
        title="OpenSearch vs Elasticsearch",
        content="A direct comparison of OpenSearch and Elasticsearch.",
        score=10.0,
    )

    signals = ranking_signals_for_hit(hit, policy)

    assert signals.comparison_intent_match > 0


def test_ranking_signals_include_recruiting_demotion():
    policy = classify_query_policy(
        "site reliability engineering",
        prepare_search_query("site reliability engineering"),
    )
    hit = SearchHit(
        url="https://open.talentio.com/r/1/c/smsc/pages/58450",
        title="Site Reliability Engineering",
        content="x",
        score=10.0,
    )

    signals = ranking_signals_for_hit(hit, policy)

    assert signals.is_recruiting_page is True


def test_ranking_signals_ignore_recruiting_for_recruiting_queries():
    policy = classify_query_policy(
        "software engineer jobs",
        prepare_search_query("software engineer jobs"),
    )
    hit = SearchHit(
        url="https://example.com/jobs/software-engineer",
        title="Software Engineer Jobs",
        content="x",
        score=10.0,
    )

    signals = ranking_signals_for_hit(hit, policy)

    assert signals.is_recruiting_page is False


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


def test_rerank_hits_promotes_sre_sources_above_generic_service_pages():
    policy = classify_query_policy(
        "site reliability engineering",
        prepare_search_query("site reliability engineering"),
    )
    hits = [
        SearchHit(
            url="https://serokell.io/ci-cd-and-sre-services",
            title="Site reliability engineering services",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://sre.google/",
            title="Google SRE - Site Reliability Engineering",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://www.usenix.org/conference/srecon18asia/presentation/purgason",
            title="The Evolution of Site Reliability Engineering",
            content="x",
            score=8.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://sre.google/",
        "https://www.usenix.org/conference/srecon18asia/presentation/purgason",
        "https://serokell.io/ci-cd-and-sre-services",
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
            url="https://openai.com/news/",
            title="News | OpenAI",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://openai.com/index/introducing-gpt-6/",
            title="Introducing GPT-6",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://openai.com/news/",
        "https://openai.com/index/introducing-gpt-6/",
        "https://community.openai.com/t/openai-dev-day-2023-announcement/472706",
    ]


def test_rerank_hits_promotes_python_release_notes_paths():
    policy = classify_query_policy(
        "Python release notes",
        prepare_search_query("Python release notes"),
    )
    hits = [
        SearchHit(
            url="https://docs.python.org/3/using/windows.html",
            title="Using Python on Windows",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.python.org/3/whatsnew/",
            title="What's New In Python",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://docs.python.org/3/library/py_compile.html",
            title="py_compile",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.python.org/3/whatsnew/",
        "https://docs.python.org/3/using/windows.html",
        "https://docs.python.org/3/library/py_compile.html",
    ]


def test_rerank_hits_promotes_django_release_notes_paths():
    policy = classify_query_policy(
        "Django release notes",
        prepare_search_query("Django release notes"),
    )
    hits = [
        SearchHit(
            url="https://docs.djangoproject.com/en/dev/internals/contributing/localizing/",
            title="Localizing Django",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.djangoproject.com/en/dev/releases/",
            title="Release notes",
            content="x",
            score=5.0,
        ),
        SearchHit(
            url="https://docs.djangoproject.com/en/dev/faq/install/",
            title="FAQ: Installation",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.djangoproject.com/en/dev/releases/",
        "https://docs.djangoproject.com/en/dev/internals/contributing/localizing/",
        "https://docs.djangoproject.com/en/dev/faq/install/",
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


def test_rerank_hits_promotes_docker_compose_file_reference():
    policy = classify_query_policy(
        "Docker compose file reference",
        prepare_search_query("Docker compose file reference"),
    )
    hits = [
        SearchHit(
            url="https://docs.docker.com/compose/completion/",
            title="Docker Compose | Docker Docs",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.docker.com/compose/reference/up/",
            title="docker compose up | Docker Docs",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://docs.docker.com/compose/compose-file/",
            title="Compose file reference | Docker Docs",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.docker.com/compose/compose-file/",
        "https://docs.docker.com/compose/reference/up/",
        "https://docs.docker.com/compose/completion/",
    ]


def test_rerank_hits_promotes_pytest_fixture_page():
    policy = classify_query_policy(
        "pytest fixture",
        prepare_search_query("pytest fixture"),
    )
    hits = [
        SearchHit(
            url="https://docs.pytest.org/en/6.2.x/contents.html",
            title="Full pytest documentation",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://docs.pytest.org/en/stable/explanation/types.html",
            title="Typing in pytest",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://docs.pytest.org/en/6.2.x/fixture.html",
            title="pytest fixtures: explicit, modular, scalable",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://docs.pytest.org/en/6.2.x/fixture.html",
        "https://docs.pytest.org/en/6.2.x/contents.html",
        "https://docs.pytest.org/en/stable/explanation/types.html",
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


def test_rerank_hits_demotes_low_signal_pricing_pages_for_comparison_queries():
    policy = classify_query_policy(
        "OpenSearch vs Elasticsearch",
        prepare_search_query("OpenSearch vs Elasticsearch"),
    )
    hits = [
        SearchHit(
            url="https://bonsai.io/pricing",
            title="Bonsai Pricing | Fully Managed Elasticsearch & OpenSearch",
            content="Pricing and plans for managed search",
            score=10.0,
        ),
        SearchHit(
            url="https://www.chaossearch.io/blog/opensearch-vs-elasticsearch-comparison",
            title="OpenSearch vs. Elasticsearch: Which Is Better?",
            content="A direct comparison of OpenSearch and Elasticsearch.",
            score=9.0,
        ),
        SearchHit(
            url="https://sematext.com/opensearch-vs-elasticsearch-which-one-is-better-sematext/",
            title="OpenSearch vs Elasticsearch: Which One Is Better to Use?",
            content="Explicit comparison of OpenSearch and Elasticsearch.",
            score=8.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://www.chaossearch.io/blog/opensearch-vs-elasticsearch-comparison",
        "https://sematext.com/opensearch-vs-elasticsearch-which-one-is-better-sematext/",
        "https://bonsai.io/pricing",
    ]


def test_rerank_hits_demotes_cue_only_pages_without_subjects_in_title():
    policy = classify_query_policy(
        "Redis vs Memcached",
        prepare_search_query("Redis vs Memcached"),
    )
    hits = [
        SearchHit(
            url="https://www.site24x7.com/learn/memcached-vs-redis-comparison.html",
            title="Memcached vs Redis: Key Differences Explained - Site24x7",
            content="Redis and Memcached are compared directly.",
            score=10.0,
        ),
        SearchHit(
            url="https://www.site24x7.jp/zabbix-alternative.html",
            title="Zabbix vs SaaS Comparison",
            content="Includes EC Redis nodes and EC Memcached nodes in a generic monitoring page.",
            score=9.0,
        ),
        SearchHit(
            url="https://aws.amazon.com/elasticache/redis-vs-memcached/",
            title="Redis OSS vs. Memcached - Difference Between Caches - AWS",
            content="Compare Redis and Memcached.",
            score=8.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://www.site24x7.com/learn/memcached-vs-redis-comparison.html",
        "https://aws.amazon.com/elasticache/redis-vs-memcached/",
        "https://www.site24x7.jp/zabbix-alternative.html",
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


def test_rerank_hits_prefers_go_docs_entry_page():
    policy = classify_query_policy(
        "Go documentation",
        prepare_search_query("Go documentation"),
    )
    hits = [
        SearchHit(
            url="https://docs.fly.jfrog.ai/package-managers/go/",
            title="Go :: JFrog Fly Documentation",
            content="x",
            score=10.0,
        ),
        SearchHit(
            url="https://www.wireshark.org/docs/",
            title="Wireshark Documentation",
            content="x",
            score=9.0,
        ),
        SearchHit(
            url="https://go.dev/doc",
            title="Documentation - The Go Programming Language",
            content="x",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://go.dev/doc",
        "https://docs.fly.jfrog.ai/package-managers/go/",
        "https://www.wireshark.org/docs/",
    ]


def test_rerank_hits_promotes_explicit_comparison_over_single_product_roots():
    policy = classify_query_policy(
        "FastAPI vs Django",
        prepare_search_query("FastAPI vs Django"),
    )
    hits = [
        SearchHit(
            url="https://fastapi.tiangolo.com/",
            title="FastAPI",
            content="FastAPI framework for APIs",
            score=10.0,
        ),
        SearchHit(
            url="https://fastapi.tiangolo.com/zh/",
            title="FastAPI",
            content="FastAPI docs in Chinese",
            score=9.0,
        ),
        SearchHit(
            url="https://betterstack.com/community/guides/scaling-python/django-vs-fastapi/",
            title="Django vs FastAPI: Choosing the Right Python Web Framework",
            content="Compare Django and FastAPI for different backend workloads.",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://betterstack.com/community/guides/scaling-python/django-vs-fastapi/",
        "https://fastapi.tiangolo.com/",
        "https://fastapi.tiangolo.com/zh/",
    ]


def test_rerank_hits_demotes_duplicate_domains_for_comparison_queries():
    policy = classify_query_policy(
        "OpenSearch vs Elasticsearch",
        prepare_search_query("OpenSearch vs Elasticsearch"),
    )
    hits = [
        SearchHit(
            url="https://bonsai.io/",
            title="Bonsai | Fully Managed Elasticsearch & OpenSearch",
            content="Managed service for Elasticsearch and OpenSearch.",
            score=10.0,
        ),
        SearchHit(
            url="https://www.bonsai.io/about",
            title="About Bonsai | Fully Managed Elasticsearch & OpenSearch",
            content="About managed Elasticsearch and OpenSearch.",
            score=9.0,
        ),
        SearchHit(
            url="https://sematext.com/opensearch-vs-elasticsearch-which-one-is-better-sematext/",
            title="OpenSearch vs Elasticsearch: Which One Is Better?",
            content="Detailed comparison of OpenSearch vs Elasticsearch.",
            score=4.0,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=3)

    assert [hit.url for hit in reranked] == [
        "https://sematext.com/opensearch-vs-elasticsearch-which-one-is-better-sematext/",
        "https://bonsai.io/",
        "https://www.bonsai.io/about",
    ]


def test_rerank_hits_uses_link_ranks_as_weak_tie_break():
    policy = classify_query_policy("GitHub docs", prepare_search_query("GitHub docs"))
    hits = [
        SearchHit(
            url="https://docs.github.com/en/actions",
            title="Actions",
            content="x",
            score=10.0,
            page_rank=0.2,
            domain_rank=0.4,
        ),
        SearchHit(
            url="https://docs.github.com/en/copilot",
            title="Copilot",
            content="x",
            score=9.0,
            page_rank=0.6,
            domain_rank=0.1,
        ),
    ]

    reranked = rerank_hits(hits, policy, limit=2)

    assert [hit.url for hit in reranked] == [
        "https://docs.github.com/en/copilot",
        "https://docs.github.com/en/actions",
    ]
