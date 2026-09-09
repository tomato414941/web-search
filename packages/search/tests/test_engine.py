"""Exercise the search entry point without a Web app or database."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from web_search_engine import SearchEngine


def test_engine_retrieves_and_ranks_using_injected_client():
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

    result = SearchEngine(client, index="evaluation-documents").search("GitHub", 2)

    assert client.search.call_args.kwargs["index"] == "evaluation-documents"
    assert result.total == 2
    assert [hit.url for hit in result.hits] == [
        "https://github.com/",
        "https://github.com/org/repo",
    ]
    # The engine returns domain results, before HTML snippets or telemetry IDs.
    assert result.hits[0].content == "GitHub home"
    assert result.hits[0].score == 5.0


def test_engine_empty_query_does_not_access_backend():
    client = Mock()
    result = SearchEngine(client).search("", 5)
    assert result.hits == []
    assert result.per_page == 5
    client.search.assert_not_called()


def test_engine_propagates_backend_failure_to_caller():
    client = Mock()
    client.search.side_effect = RuntimeError("backend unavailable")
    with pytest.raises(RuntimeError, match="backend unavailable"):
        SearchEngine(client).search("test")


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
assert SearchEngine(object()).search('').hits == []
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
