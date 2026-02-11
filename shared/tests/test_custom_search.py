"""
Tests for Custom Full-Text Search Engine
"""

import os
import sqlite3
import pytest
import numpy as np
from shared.db.search import open_db
from shared.search.indexer import SearchIndexer
from shared.search.searcher import SearchEngine
from shared.search.scoring import BM25Config


@pytest.fixture
def temp_search_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test_custom_search.db")
    conn = open_db(db_path)
    conn.close()
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


class TestSearchIndexer:
    """Tests for SearchIndexer."""

    def test_index_single_document(self, temp_search_db):
        """Test indexing a single document."""
        indexer = SearchIndexer(temp_search_db)

        indexer.index_document(
            url="http://example.com/1",
            title="東京観光ガイド",
            content="東京スカイツリーと浅草寺の観光情報。",
        )
        indexer.update_global_stats()

        # Verify document is stored
        import sqlite3

        conn = sqlite3.connect(temp_search_db)
        doc = conn.execute(
            "SELECT title, word_count FROM documents WHERE url = ?",
            ("http://example.com/1",),
        ).fetchone()
        conn.close()

        assert doc is not None
        assert doc[0] == "東京観光ガイド"
        assert doc[1] > 0  # word_count should be set

    def test_index_creates_inverted_index(self, temp_search_db):
        """Test that indexing creates inverted index entries."""
        indexer = SearchIndexer(temp_search_db)

        indexer.index_document(
            url="http://example.com/1",
            title="Python入門",
            content="Pythonは人気のプログラミング言語です。",
        )

        import sqlite3

        conn = sqlite3.connect(temp_search_db)
        # Check for token in inverted index
        entries = conn.execute(
            "SELECT token, field, term_freq FROM inverted_index WHERE url = ?",
            ("http://example.com/1",),
        ).fetchall()
        conn.close()

        assert len(entries) > 0
        tokens = [e[0] for e in entries]
        # SudachiPy should tokenize "Python" as "python" (lowercase)
        assert any("python" in t.lower() for t in tokens) or any(
            "Python" in t for t in tokens
        )

    def test_delete_document(self, temp_search_db):
        """Test deleting a document removes all index entries."""
        indexer = SearchIndexer(temp_search_db)

        url = "http://example.com/delete-me"
        indexer.index_document(
            url=url, title="削除テスト", content="このページは削除されます。"
        )
        indexer.delete_document(url)

        import sqlite3

        conn = sqlite3.connect(temp_search_db)
        doc = conn.execute("SELECT * FROM documents WHERE url = ?", (url,)).fetchone()
        index_entries = conn.execute(
            "SELECT * FROM inverted_index WHERE url = ?", (url,)
        ).fetchall()
        conn.close()

        assert doc is None
        assert len(index_entries) == 0


class TestSearchEngine:
    """Tests for SearchEngine."""

    def test_basic_search(self, temp_search_db):
        """Test basic AND search."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Index test documents
        indexer.index_document(
            url="http://example.com/tokyo",
            title="東京観光",
            content="東京タワーと浅草寺。",
        )
        indexer.index_document(
            url="http://example.com/kyoto",
            title="京都観光",
            content="金閣寺と清水寺。",
        )
        indexer.update_global_stats()

        # Search for 東京
        result = engine.search("東京")

        assert result.total >= 1
        urls = [h.url for h in result.hits]
        assert "http://example.com/tokyo" in urls
        # 京都 should not match 東京
        assert "http://example.com/kyoto" not in urls

    def test_or_search(self, temp_search_db):
        """Test OR logic - documents with any token match, full match ranks higher."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        indexer.index_document(
            url="http://example.com/1",
            title="Python と JavaScript",
            content="両方の言語を使う。",
        )
        indexer.index_document(
            url="http://example.com/2",
            title="Pythonのみ",
            content="Pythonだけを使う。",
        )
        indexer.update_global_stats()

        # Search for "Python JavaScript" should match both docs (OR logic)
        result = engine.search("Python JavaScript")

        assert result.total == 2
        # Doc with both tokens should rank higher
        assert result.hits[0].url == "http://example.com/1"

    def test_empty_query(self, temp_search_db):
        """Test that empty query returns empty result."""
        engine = SearchEngine(temp_search_db)

        result = engine.search("")
        assert result.total == 0
        assert len(result.hits) == 0

    def test_no_matches(self, temp_search_db):
        """Test query with no matches."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        indexer.index_document(
            url="http://example.com/1",
            title="りんご",
            content="赤いりんご。",
        )
        indexer.update_global_stats()

        result = engine.search("バナナ")
        assert result.total == 0

    def test_title_boost(self, temp_search_db):
        """Test that title matches are scored higher."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Doc 1: keyword in title
        indexer.index_document(
            url="http://example.com/title",
            title="Python入門",
            content="プログラミングの基礎。",
        )
        # Doc 2: keyword in content only
        indexer.index_document(
            url="http://example.com/content",
            title="プログラミング基礎",
            content="Pythonを学ぶ。",
        )
        indexer.update_global_stats()

        result = engine.search("Python")

        assert result.total == 2
        # Title match should rank higher
        assert result.hits[0].url == "http://example.com/title"

    def test_pagination(self, temp_search_db):
        """Test pagination works correctly."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Index 5 documents
        for i in range(5):
            indexer.index_document(
                url=f"http://example.com/{i}",
                title=f"テスト文書 {i}",
                content="テスト内容。",
            )
        indexer.update_global_stats()

        # Get page 1 with 2 results
        result1 = engine.search("テスト", limit=2, page=1)
        assert len(result1.hits) == 2
        assert result1.page == 1
        assert result1.last_page == 3

        # Get page 2
        result2 = engine.search("テスト", limit=2, page=2)
        assert len(result2.hits) == 2
        assert result2.page == 2

        # Get page 3 (last page, only 1 result)
        result3 = engine.search("テスト", limit=2, page=3)
        assert len(result3.hits) == 1

    def test_case_insensitive_search(self, temp_search_db):
        """Test that search is case-insensitive."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        indexer.index_document(
            url="http://example.com/claude",
            title="Claude AI Assistant",
            content="Claude is made by Anthropic.",
        )
        indexer.update_global_stats()

        # Lowercase query should find uppercase content
        result = engine.search("claude")
        assert result.total >= 1
        assert result.hits[0].url == "http://example.com/claude"

        # Uppercase query should also work
        result2 = engine.search("CLAUDE")
        assert result2.total >= 1
        assert result2.hits[0].url == "http://example.com/claude"

    def test_or_search_ranking(self, temp_search_db):
        """Test that documents matching more tokens rank higher."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        indexer.index_document(
            url="http://example.com/both",
            title="Python JavaScript tutorial",
            content="Learn Python and JavaScript together.",
        )
        indexer.index_document(
            url="http://example.com/one",
            title="Ruby tutorial",
            content="Learn Ruby programming.",
        )
        indexer.update_global_stats()

        result = engine.search("Python JavaScript Ruby")
        assert result.total == 2
        # Document with more token matches should rank first
        assert result.hits[0].url == "http://example.com/both"

    def test_stop_words_filtered(self, temp_search_db):
        """Test that stop words are filtered from indexing and search."""
        indexer = SearchIndexer(temp_search_db)

        indexer.index_document(
            url="http://example.com/1",
            title="Python programming",
            content="Python is the best language.",
        )
        indexer.update_global_stats()

        # Check that stop words like "is", "the" are not in the index
        import sqlite3

        conn = sqlite3.connect(temp_search_db)
        stop_entries = conn.execute(
            "SELECT token FROM inverted_index WHERE token IN ('is', 'the')"
        ).fetchall()
        conn.close()

        assert len(stop_entries) == 0


class TestBM25Scoring:
    """Tests for BM25 scoring algorithm."""

    def test_bm25_idf_rare_term_higher(self, temp_search_db):
        """Test that rare terms have higher IDF and thus higher scores."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Create multiple documents with common term "Python"
        for i in range(10):
            indexer.index_document(
                url=f"http://example.com/common{i}",
                title=f"Python文書{i}",
                content="Pythonは人気です。",
            )

        # Create one document with rare term "Haskell"
        indexer.index_document(
            url="http://example.com/rare",
            title="Haskell入門",
            content="Haskellは関数型言語。",
        )
        indexer.update_global_stats()

        # Search for Haskell (rare) should give higher score per match
        result = engine.search("Haskell")
        assert result.total == 1
        haskell_score = result.hits[0].score

        # Search for Python (common)
        result2 = engine.search("Python")
        assert result2.total == 10
        # Each Python match should have lower score due to lower IDF
        python_score = result2.hits[0].score

        # Haskell should have higher score (higher IDF)
        assert haskell_score > python_score

    def test_bm25_term_frequency_saturation(self, temp_search_db):
        """Test that BM25 saturates term frequency (not linear)."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Doc with term appearing once
        indexer.index_document(
            url="http://example.com/once",
            title="テスト",
            content="Python を使う",
        )
        # Doc with term appearing many times
        indexer.index_document(
            url="http://example.com/many",
            title="テスト",
            content="Python Python Python Python Python Python Python Python を使う",
        )
        indexer.update_global_stats()

        result = engine.search("Python")

        # Both should match
        assert result.total == 2

        # Find scores
        scores = {h.url: h.score for h in result.hits}

        # The "many" doc should score higher but not 8x higher (saturation)
        ratio = scores["http://example.com/many"] / scores["http://example.com/once"]
        assert ratio > 1  # Higher is expected
        assert ratio < 4  # But not linear (8x would be linear)

    def test_bm25_length_normalization(self, temp_search_db):
        """Test that longer documents are normalized."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Short document with keyword
        indexer.index_document(
            url="http://example.com/short",
            title="短い文書",
            content="Python programming language basics",
        )
        # Long document with same keyword (once) but much more text
        indexer.index_document(
            url="http://example.com/long",
            title="長い文書",
            content="Python " + " ".join(f"word{i}" for i in range(200)),
        )
        indexer.update_global_stats()

        result = engine.search("Python")
        assert result.total == 2

        scores = {h.url: h.score for h in result.hits}

        # Short doc should score higher (length normalization)
        assert scores["http://example.com/short"] > scores["http://example.com/long"]

    def test_pagerank_integration(self, temp_search_db):
        """Test that PageRank boosts document scores."""
        indexer = SearchIndexer(temp_search_db)

        # Index two similar documents
        indexer.index_document(
            url="http://example.com/popular",
            title="Python入門",
            content="Pythonの基礎を学ぶ",
        )
        indexer.index_document(
            url="http://example.com/unpopular",
            title="Python入門",
            content="Pythonの基礎を学ぶ",
        )
        indexer.update_global_stats()

        # Set PageRank scores (popular page has higher score)
        conn = sqlite3.connect(temp_search_db)
        conn.execute(
            "INSERT INTO page_ranks (url, score) VALUES (?, ?)",
            ("http://example.com/popular", 0.8),
        )
        conn.execute(
            "INSERT INTO page_ranks (url, score) VALUES (?, ?)",
            ("http://example.com/unpopular", 0.1),
        )
        conn.commit()
        conn.close()

        # Search with PageRank enabled (default)
        engine = SearchEngine(temp_search_db)
        result = engine.search("Python")

        assert result.total == 2
        # Popular page should rank first due to PageRank boost
        assert result.hits[0].url == "http://example.com/popular"

    def test_pagerank_multiplicative_effect(self, temp_search_db):
        """Test that PageRank applies multiplicative boost to BM25 scores."""
        indexer = SearchIndexer(temp_search_db)

        indexer.index_document(
            url="http://example.com/a",
            title="Python入門",
            content="Pythonの基礎を学ぶ",
        )
        indexer.update_global_stats()

        # Set high PageRank (normalized 0-1 scale)
        conn = sqlite3.connect(temp_search_db)
        conn.execute(
            "INSERT INTO page_ranks (url, score) VALUES (?, ?)",
            ("http://example.com/a", 1.0),
        )
        conn.commit()
        conn.close()

        # Score with PageRank enabled (weight=0.5)
        engine_with_pr = SearchEngine(
            temp_search_db, bm25_config=BM25Config(pagerank_weight=0.5)
        )
        result_with = engine_with_pr.search("Python")
        score_with = result_with.hits[0].score

        # Score with PageRank disabled
        engine_no_pr = SearchEngine(
            temp_search_db, bm25_config=BM25Config(pagerank_weight=0.0)
        )
        result_without = engine_no_pr.search("Python")
        score_without = result_without.hits[0].score

        # Multiplicative: score_with = score_without * (1 + 0.5 * 1.0) = 1.5x
        assert score_with == pytest.approx(score_without * 1.5, rel=1e-6)

    def test_pagerank_disabled(self, temp_search_db):
        """Test that PageRank can be disabled."""
        indexer = SearchIndexer(temp_search_db)

        indexer.index_document(
            url="http://example.com/popular",
            title="Python入門",
            content="Pythonの基礎を学ぶ",
        )
        indexer.index_document(
            url="http://example.com/unpopular",
            title="Python入門ガイド",  # Slightly different title
            content="Pythonの基礎を学ぶ",
        )
        indexer.update_global_stats()

        # Set PageRank (unpopular has high PR but we'll disable it)
        conn = sqlite3.connect(temp_search_db)
        conn.execute(
            "INSERT INTO page_ranks (url, score) VALUES (?, ?)",
            ("http://example.com/popular", 0.1),
        )
        conn.execute(
            "INSERT INTO page_ranks (url, score) VALUES (?, ?)",
            ("http://example.com/unpopular", 0.9),
        )
        conn.commit()
        conn.close()

        # Search with PageRank disabled
        config = BM25Config(pagerank_weight=0.0)
        engine = SearchEngine(temp_search_db, bm25_config=config)
        result = engine.search("Python")

        # Without PageRank, ordering depends only on BM25
        # Both have similar content, so scores should be close
        assert result.total == 2
        scores = [h.score for h in result.hits]
        # Scores should be similar (within 50%) when PR is disabled
        assert abs(scores[0] - scores[1]) / max(scores) < 0.5

    def test_pagerank_dangling_nodes(self, temp_search_db):
        """Dangling nodes (no outlinks) should still receive PageRank."""
        from shared.pagerank import calculate_pagerank

        indexer = SearchIndexer(temp_search_db)
        # A → B → C (C has no outlinks = dangling)
        for url in ["http://a.com/", "http://b.com/", "http://c.com/"]:
            indexer.index_document(url=url, title="Test", content="test")
        indexer.update_global_stats()

        conn = sqlite3.connect(temp_search_db)
        conn.execute(
            "INSERT INTO links (src, dst) VALUES (?, ?)",
            ("http://a.com/", "http://b.com/"),
        )
        conn.execute(
            "INSERT INTO links (src, dst) VALUES (?, ?)",
            ("http://b.com/", "http://c.com/"),
        )
        conn.commit()
        conn.close()

        calculate_pagerank(temp_search_db)

        conn = sqlite3.connect(temp_search_db)
        rows = conn.execute("SELECT url, score FROM page_ranks").fetchall()
        conn.close()
        scores = {url: score for url, score in rows}

        assert len(scores) == 3
        # C is linked to by B, so it should have a meaningful score (not near-zero)
        assert scores["http://c.com/"] > 0.1
        # All scores should be positive
        assert all(s > 0 for s in scores.values())


class TestHybridSearch:
    """Tests for Hybrid (RRF) search."""

    def test_hybrid_search_combines_results(self, temp_search_db):
        """Test that hybrid search combines BM25 results (no vector without embeddings)."""
        indexer = SearchIndexer(temp_search_db)
        engine = SearchEngine(temp_search_db)

        # Index documents
        indexer.index_document(
            url="http://example.com/1",
            title="Python入門",
            content="Pythonの基礎を学ぶ",
        )
        indexer.index_document(
            url="http://example.com/2",
            title="Pythonガイド",
            content="Python初心者向け",
        )
        indexer.update_global_stats()

        # Hybrid search without vector embeddings falls back to BM25 only
        result = engine.hybrid_search("Python")

        assert result.total == 2
        assert len(result.hits) == 2
        # RRF scores should be present
        assert all(h.score > 0 for h in result.hits)

    def test_hybrid_search_with_mock_embeddings(self, temp_search_db):
        """Test hybrid search with mock embedding functions."""
        indexer = SearchIndexer(temp_search_db)

        # Index documents
        indexer.index_document(
            url="http://example.com/bm25",
            title="Python programming",
            content="Learn Python programming language",
        )
        indexer.index_document(
            url="http://example.com/semantic",
            title="Coding tutorial",
            content="Software development basics",
        )
        indexer.update_global_stats()

        # Set up mock embeddings
        # - "Python programming" doc gets vector [1, 0, 0]
        # - "Coding tutorial" doc gets vector [0, 1, 0]
        # - Query "Python" gets vector [0.9, 0.1, 0] (similar to first doc)
        import struct

        def serialize(vec):
            return struct.pack(f"{len(vec)}f", *vec)

        def deserialize(blob):
            count = len(blob) // 4
            return np.array(struct.unpack(f"{count}f", blob))

        # Insert mock embeddings
        conn = sqlite3.connect(temp_search_db)
        conn.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)",
            ("http://example.com/bm25", serialize([1.0, 0.0, 0.0])),
        )
        conn.execute(
            "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)",
            ("http://example.com/semantic", serialize([0.0, 1.0, 0.0])),
        )
        conn.commit()
        conn.close()

        # Create engine with mock functions
        def mock_embed(text):
            if "python" in text.lower():
                return np.array([0.9, 0.1, 0.0])
            return np.array([0.1, 0.9, 0.0])

        engine = SearchEngine(
            temp_search_db,
            embed_query_func=mock_embed,
            deserialize_func=deserialize,
        )

        # BM25 search should find "Python programming"
        bm25_result = engine.search("Python")
        assert bm25_result.total == 1
        assert bm25_result.hits[0].url == "http://example.com/bm25"

        # Vector search should also prefer "Python programming" (similar vector)
        vector_result = engine.vector_search("Python")
        assert vector_result.total == 2  # Returns all docs sorted by similarity
        assert vector_result.hits[0].url == "http://example.com/bm25"

        # Hybrid should combine both
        hybrid_result = engine.hybrid_search("Python")
        assert hybrid_result.total >= 1
        # First result should be "Python programming" (strong in both)
        assert hybrid_result.hits[0].url == "http://example.com/bm25"

    def test_vector_search_empty_without_config(self, temp_search_db):
        """Test that vector search returns empty without embedding functions."""
        engine = SearchEngine(temp_search_db)

        result = engine.vector_search("test")
        assert result.total == 0
        assert len(result.hits) == 0


class TestSnippetGeneration:
    """Tests for snippet generation."""

    def test_basic_snippet(self):
        """Test basic snippet generation with highlighting."""
        from shared.search.snippet import generate_snippet

        text = "Python is a programming language. Python is popular."
        snippet = generate_snippet(text, ["Python"])

        assert "Python" in snippet.plain_text
        assert "<mark>Python</mark>" in snippet.text

    def test_snippet_context_window(self):
        """Test that snippet shows context around match."""
        from shared.search.snippet import generate_snippet

        # Long text with keyword in the middle
        text = "A" * 100 + " Python " + "B" * 100
        snippet = generate_snippet(text, ["Python"], window_size=50)

        # Should contain Python and be approximately window_size
        assert "Python" in snippet.plain_text
        assert len(snippet.plain_text) < 150  # Roughly window_size + ellipsis

    def test_snippet_ellipsis(self):
        """Test that ellipsis is added when text is truncated."""
        from shared.search.snippet import generate_snippet

        text = "Start " + "X" * 200 + " Python " + "Y" * 200 + " End"
        snippet = generate_snippet(text, ["Python"], window_size=50)

        # Should have ellipsis at start and end
        assert snippet.plain_text.startswith("...")
        assert snippet.plain_text.endswith("...")

    def test_snippet_no_highlight(self):
        """Test snippet without HTML highlighting."""
        from shared.search.snippet import generate_snippet

        text = "Python is great"
        snippet = generate_snippet(text, ["Python"], highlight=False)

        assert "<mark>" not in snippet.text
        assert snippet.text == snippet.plain_text

    def test_snippet_empty_terms(self):
        """Test snippet with no search terms."""
        from shared.search.snippet import generate_snippet

        text = "Some text content here"
        snippet = generate_snippet(text, [], window_size=10)

        assert snippet.text == "Some text ..."

    def test_snippet_no_match(self):
        """Test snippet when terms don't match."""
        from shared.search.snippet import generate_snippet

        text = "This text has no matches"
        snippet = generate_snippet(text, ["Python"])

        # Should return beginning of text
        assert snippet.text.startswith("This text")

    def test_highlight_snippet_function(self):
        """Test the convenience highlight_snippet function."""
        from shared.search.snippet import highlight_snippet

        text = "Learn Python today"
        result = highlight_snippet(text, ["Python"])

        assert "<mark>Python</mark>" in result
        assert isinstance(result, str)

    def test_html_escape_in_snippet(self):
        """Test that HTML entities in content are escaped."""
        from shared.search.snippet import generate_snippet

        text = "Use <div> tags and & symbols in Python code"
        snippet = generate_snippet(text, ["Python"])

        assert "&lt;div&gt;" in snippet.text
        assert "&amp;" in snippet.text
        assert "<mark>Python</mark>" in snippet.text
        # Plain text should NOT be escaped
        assert "<div>" in snippet.plain_text

    def test_xss_prevention_in_snippet(self):
        """Test that script tags in content are neutralized."""
        from shared.search.snippet import generate_snippet

        text = '<script>alert("xss")</script> Python is safe'
        snippet = generate_snippet(text, ["Python"])

        assert "<script>" not in snippet.text
        assert "&lt;script&gt;" in snippet.text
        assert "<mark>Python</mark>" in snippet.text

    def test_html_escape_in_matched_term(self):
        """Test that matched terms with special chars are escaped."""
        from shared.search.snippet import generate_snippet

        text = "Search for A&B in the document"
        snippet = generate_snippet(text, ["A&B"])

        assert "<mark>A&amp;B</mark>" in snippet.text
        assert "A&B" in snippet.plain_text
