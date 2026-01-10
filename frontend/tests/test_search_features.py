import pytest
import os
from typing import Generator

from shared.db.sqlite import open_db, upsert_page
from frontend.services.search import SearchService
from frontend.indexer.analyzer import analyzer


# Fixture to create a temporary database for testing
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


def test_japanese_tokenization(temp_db):
    """
    Verify SudachiPy integration and FTS5 behavior.
    Replaces scripts/verify_tokenization.py
    """
    con = open_db(temp_db)

    # Insert Data
    # 1. Page with Tokyo
    title1 = "東京都の観光"
    content1 = "東京スカイツリーと浅草寺。"
    # Tokenize
    t1_idx = analyzer.tokenize(title1)
    c1_idx = analyzer.tokenize(content1)
    upsert_page(con, "http://example.com/tokyo", t1_idx, c1_idx, title1, content1)

    # 2. Page with Kyoto
    title2 = "京都の歴史"
    content2 = "金閣寺と清水寺。"
    t2_idx = analyzer.tokenize(title2)
    c2_idx = analyzer.tokenize(content2)
    upsert_page(con, "http://example.com/kyoto", t2_idx, c2_idx, title2, content2)

    con.commit()
    con.close()

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


def test_display_text_raw(temp_db):
    """
    Verify that search results return Raw Title, not Tokenized Title.
    Replaces scripts/verify_display_text.py
    """
    con = open_db(temp_db)

    raw_title = "東京都の観光"
    tokenized_title = analyzer.tokenize(raw_title)  # "東京 都 の 観光"

    # Verify assumption
    assert " " in tokenized_title
    assert " " not in raw_title

    upsert_page(
        con,
        "http://example.com/1",
        tokenized_title,
        "content",
        raw_title,
        "raw_content",
    )
    con.commit()
    con.close()

    svc = SearchService(db_path=temp_db)
    res = svc.search("東京")

    assert len(res["hits"]) > 0
    hit = res["hits"][0]

    # The title in the hit should be the Raw Title (No spaces)
    assert hit["title"] == raw_title
    assert " " not in hit["title"]
