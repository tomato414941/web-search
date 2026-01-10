import random
import sys
import os

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from web_search.db.sqlite import open_db, upsert_page
from web_search.core.config import settings
from web_search.services.embedding import embedding_service
from web_search.indexer.analyzer import analyzer

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


def inject_data(count: int = 50):
    print(f"Injecting {count} dummy pages into {settings.DB_PATH}...")

    # Ensure directory
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)

    con = open_db(settings.DB_PATH)
    try:
        for i in range(count):
            topic, content_base = random.choice(SAMPLE_TOPICS)

            # Randomize title and content to create variety
            # Case 1: Title matches topic exactly
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

            # Analyze (Tokenize) for FTS
            if title:
                idx_title = analyzer.analyze(title)
            else:
                idx_title = ""

            if content:
                idx_content = analyzer.analyze(content)
            else:
                idx_content = ""

            upsert_page(con, url, idx_title, idx_content, title, content)

            # Embeddings (Title + Content)
            # Combine them for semantic search
            text_to_embed = f"{title}. {content}"
            vector_blob = embedding_service.embed(text_to_embed)
            con.execute("DELETE FROM page_embeddings WHERE url=?", (url,))
            con.execute(
                "INSERT INTO page_embeddings (url, embedding) VALUES (?, ?)",
                (url, vector_blob),
            )

            # Generate Links using standard SQL
            # Create a "Hub" page at index 0 (http://example.com/page/0)
            # Let many pages link to page/0
            if i > 0 and random.random() < 0.5:
                # 50% chance to link to the Hub (Page 0)
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
        upsert_page(
            con,
            "http://example.com/page/0",
            "The Popular Hub Page",
            "This page is very popular. Ideally it ranks high.",
        )

        con.commit()
        print("Injection complete.")
    finally:
        con.close()


if __name__ == "__main__":
    inject_data()
