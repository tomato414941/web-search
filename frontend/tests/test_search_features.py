import pytest
import os
from typing import Generator
from unittest.mock import patch
import numpy as np

from shared.db.search import open_db
from shared.search import SearchIndexer
from frontend.services.search import SearchService
from shared.analyzer import analyzer


@pytest.fixture
def temp_db(tmp_path) -> Generator[str, None, None]:
    db_path = tmp_path / "test_search.db"
    str_path = str(db_path)

    # Initialize DB (Schema creation)
    con = open_db(str_path)
    con.close()

    yield str_path

    # Cleanup
    if os.path.exists(str_path):
        os.remove(str_path)


@pytest.fixture
def mock_embedding():
    """Mock embedding service for hybrid search tests."""
    dummy_vec = np.zeros(1536, dtype=np.float32)
    with patch("frontend.services.search.embedding_service") as mock_embed:
        mock_embed.embed_query.return_value = dummy_vec
        mock_embed.deserialize.return_value = dummy_vec
        yield mock_embed


def test_japanese_tokenization(temp_db, mock_embedding):
    """
    Verify SudachiPy integration and custom search engine behavior.
    """
    indexer = SearchIndexer(temp_db)

    # Insert Data using new indexer
    # 1. Page with Tokyo
    title1 = "東京都の観光"
    content1 = "東京スカイツリーと浅草寺。"
    indexer.index_document("http://example.com/tokyo", title1, content1)

    # 2. Page with Kyoto
    title2 = "京都の歴史"
    content2 = "金閣寺と清水寺。"
    indexer.index_document("http://example.com/kyoto", title2, content2)

    indexer.update_global_stats()

    # Search Service connected to temp DB
    svc = SearchService(db_path=temp_db)

    # Case 1: Search "東京" -> Should hit tokyo page
    res = svc.search("東京")
    titles = [h["title"] for h in res["hits"]]
    assert "東京都の観光" in titles

    # Case 2: Search "京都" -> Should hit kyoto page, BUT NOT tokyo page
    res = svc.search("京都")
    titles = [h["title"] for h in res["hits"]]
    assert "京都の歴史" in titles
    assert "東京都の観光" not in titles  # Crucial check: No partial match on "Tokyo-To"


def test_display_text_raw(temp_db, mock_embedding):
    """
    Verify that search results return Raw Title, not Tokenized Title.
    """
    indexer = SearchIndexer(temp_db)

    raw_title = "東京都の観光"
    raw_content = "raw_content"

    # Verify tokenization assumption
    tokenized_title = analyzer.tokenize(raw_title)  # "東京 都 の 観光"
    assert " " in tokenized_title
    assert " " not in raw_title

    # Index using new indexer (stores raw title directly)
    indexer.index_document("http://example.com/1", raw_title, raw_content)
    indexer.update_global_stats()

    svc = SearchService(db_path=temp_db)
    res = svc.search("東京")

    assert len(res["hits"]) > 0
    hit = res["hits"][0]

    # The title in the hit should be the Raw Title (No spaces)
    assert hit["title"] == raw_title
    assert " " not in hit["title"]
