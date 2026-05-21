from pathlib import Path
from unittest.mock import patch

from web_search_search_config.cli import seed_from_ai_list as MODULE

_normalize_seed_url = MODULE._normalize_seed_url
load_seeds = MODULE.load_seeds
submit_seeds = MODULE.submit_seeds


def test_normalize_seed_url_preserves_exact_urls():
    assert (
        _normalize_seed_url("https://en.wikipedia.org/wiki/Okapi_BM25")
        == "https://en.wikipedia.org/wiki/Okapi_BM25"
    )
    assert (
        _normalize_seed_url("https://example.com/docs?q=bm25")
        == "https://example.com/docs?q=bm25"
    )


def test_normalize_seed_url_adds_trailing_slash_to_bare_domains():
    assert _normalize_seed_url("docs.python.org") == "https://docs.python.org/"
    assert _normalize_seed_url("https://docs.python.org") == "https://docs.python.org/"


def test_load_seeds_keeps_exact_urls(tmp_path: Path):
    seed_file = tmp_path / "ai_seeds.csv"
    seed_file.write_text(
        "\n".join(
            [
                "# comment",
                "reference,https://en.wikipedia.org/wiki/Okapi_BM25,20,BM25 overview",
                "docs,docs.python.org,30,Python docs",
            ]
        ),
        encoding="utf-8",
    )

    groups = load_seeds(seed_file, include_canonical=False)

    assert groups == {
        "reference": ["https://en.wikipedia.org/wiki/Okapi_BM25"],
        "docs": ["docs.python.org"],
    }


def test_load_seeds_merges_canonical_seed_rows(tmp_path: Path):
    seed_file = tmp_path / "ai_seeds.csv"
    seed_file.write_text(
        "docs,docs.python.org,30,Python docs\n",
        encoding="utf-8",
    )

    groups = load_seeds(seed_file)

    assert "docs" in groups
    assert "docs.python.org" in groups["docs"]
    assert "https://docs.python.org/3/whatsnew/" in groups["docs"]


def test_submit_seeds_preserves_exact_urls():
    requests: list[object] = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"count": 2}'

    def _fake_urlopen(request, timeout=30):
        requests.append(request)
        return _FakeResponse()

    with patch.object(MODULE, "urlopen", side_effect=_fake_urlopen):
        added = submit_seeds(
            "http://localhost:8082",
            [
                "https://en.wikipedia.org/wiki/Okapi_BM25",
                "docs.python.org",
            ],
        )

    assert added == 2
    assert len(requests) == 1
    assert (
        requests[0].data
        == b'{"urls": ["https://en.wikipedia.org/wiki/Okapi_BM25", "https://docs.python.org/"]}'
    )
