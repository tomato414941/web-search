"""Exercise the search entry point without a Web app or database."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from web_search_engine import SearchEngine


def test_engine_preserves_native_ranking_using_injected_client():
    client = Mock()
    client.search.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_score": 10.0,
                    "_source": {
                        "url": "https://github.com/org/repo",
                        "title": "Repository",
                        "content": "A repository hosted on GitHub",
                    },
                },
                {
                    "_score": 5.0,
                    "_source": {
                        "url": "https://github.com/",
                        "title": "GitHub",
                        "content": "GitHub home",
                    },
                },
            ],
        }
    }

    result = SearchEngine(
        client, lambda text: [1.0], index="evaluation-documents"
    ).search("GitHub", 2)

    assert client.search.call_args.kwargs["index"] == "evaluation-documents"
    assert result.total == 2
    assert [hit.url for hit in result.hits] == [
        "https://github.com/org/repo",
        "https://github.com/",
    ]
    # The engine returns domain results, before HTML snippets or telemetry IDs.
    assert result.hits[0].content == "A repository hosted on GitHub"
    assert result.hits[0].score == 10.0


def test_engine_empty_query_does_not_access_backend():
    client = Mock()
    result = SearchEngine(client, lambda text: [1.0], index="test").search("", 5)
    assert result.hits == []
    assert result.per_page == 5
    client.search.assert_not_called()


def test_engine_propagates_backend_failure_to_caller():
    client = Mock()
    client.search.side_effect = RuntimeError("backend unavailable")
    with pytest.raises(RuntimeError, match="backend unavailable"):
        SearchEngine(client, lambda text: [1.0], index="test").search("test")


def test_engine_import_does_not_require_web_or_database_runtime():
    env = os.environ.copy()
    for key in ("DATABASE_URL", "ENVIRONMENT", "INDEXER_API_KEY"):
        env.pop(key, None)
    code = """
import importlib.abc
import sys

class BlockWebRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'web_search_frontend', 'web_search_postgres', 'web_search_telemetry',
            'web_search_core', 'fastapi', 'starlette', 'prometheus_client',
        }:
            raise ImportError(f'Search engine depends on Web runtime: {fullname}')

sys.meta_path.insert(0, BlockWebRuntime())
from web_search_engine import SearchEngine
assert SearchEngine(object(), lambda text: [], index="test").search('').hits == []
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_embedding_uses_original_question_without_operators():
    client = Mock()
    client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
    embed = Mock(return_value=[1.0])
    SearchEngine(client, embed, index="test").search(
        "What is Python site:example.com -snake"
    )
    embed.assert_called_once_with("What is Python")


def test_partial_results_are_errors():
    client = Mock()
    client.search.return_value = {"timed_out": True}
    with pytest.raises(RuntimeError, match="did not complete"):
        SearchEngine(client, lambda text: [1.0], index="test").search("test")


def test_invalid_page_never_calls_embedding_service():
    embed = Mock()
    with pytest.raises(ValueError):
        SearchEngine(Mock(), embed, index="test").search("test", 50, 5)
    embed.assert_not_called()
