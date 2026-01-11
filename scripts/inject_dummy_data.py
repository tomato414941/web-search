"""
Inject dummy data for testing/development.

Usage:
    python scripts/inject_dummy_data.py
"""

import random
import sys
import os

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.db.search import open_db
from shared.search import SearchIndexer

# Default DB path (can be overridden via environment)
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "search_index.db"
)

SAMPLE_TOPICS = [
    (
        "Python Web Frameworks",
        "Django vs FastAPI. FastAPI is modern and fast. Django is batteries-included.",
    ),
    (
        "FastAPI Tutorial",
        "Learn how to build APIs with FastAPI and Python. Fast execution.",
    ),
    ("Cooking Pasta", "How to cook the perfect carbonara. Use guanciale and pecorino."),
    (
        "History of Rome",
        "Rome was not built in a day. The empire lasted for centuries.",
    ),
    (
        "Machine Learning Basics",
        "Introduction to neural networks using Python and PyTorch.",
    ),
    (
        "Search Engine Optimization",
        "How to rank higher on Google using keywords in title and content.",
    ),
    ("Gardening Tips", "Grow tomatoes in your backyard. Water them daily."),
    ("React Hooks", "Using useState and useEffect in React applications."),
    (
        "Docker Containers",
        "Containerize your applications with Docker for consistent deployment.",
    ),
    ("Climate Change", "Global warming effects on agriculture and sea levels."),
    ("東京都の観光", "東京スカイツリーと浅草寺は人気の観光スポットです。"),
    ("京都の歴史", "金閣寺と清水寺。古いお寺がたくさんあります。"),
    ("美味しいラーメン", "豚骨ラーメンと醤油ラーメン。麺は硬めが好きです。"),
]


def inject_data(count: int = 50, db_path: str | None = None):
    db_path = db_path or os.environ.get("DB_PATH", DEFAULT_DB_PATH)
    print(f"Injecting {count} dummy pages into {db_path}...")

    # Ensure directory
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Initialize indexer and connection
    indexer = SearchIndexer(db_path)
    con = open_db(db_path)

    try:
        for i in range(count):
            topic, content_base = random.choice(SAMPLE_TOPICS)

            # Randomize title and content to create variety
            title = topic
            content = f"{content_base} (Page {i})"

            # Case 2: Title is generic, Content has keywords
            if random.random() < 0.3:
                title = f"Article {i}"
                content = f"{topic}. {content_base}"

            # Case 3: Title has variation
            elif random.random() < 0.3:
                title = f"{topic} Guide {i}"
                content = content_base

            url = f"http://example.com/page/{i}"

            # Index using new search engine
            indexer.index_document(url, title, content, con)

            # Generate Links
            # Create a "Hub" page at index 0 (http://example.com/page/0)
            if i > 0 and random.random() < 0.5:
                con.execute(
                    "INSERT INTO links (src, dst) VALUES (?, ?)",
                    (url, "http://example.com/page/0"),
                )

            # Random links
            for _ in range(random.randint(0, 3)):
                target_id = random.randint(0, count - 1)
                target_url = f"http://example.com/page/{target_id}"
                if target_url != url:
                    con.execute(
                        "INSERT INTO links (src, dst) VALUES (?, ?)", (url, target_url)
                    )

        # Ensure page 0 is authoritative
        indexer.index_document(
            "http://example.com/page/0",
            "The Popular Hub Page",
            "This page is very popular. Ideally it ranks high.",
            con,
        )

        # Update global stats for BM25
        indexer.update_global_stats(con)

        con.commit()
        print("Injection complete.")
    finally:
        con.close()


if __name__ == "__main__":
    inject_data()
