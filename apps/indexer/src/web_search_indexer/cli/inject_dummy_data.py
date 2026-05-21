"""Inject dummy data for testing and development."""

import argparse
import os
import random

from web_search_postgres import open_db
from web_search_indexer.services.document_indexer import SearchIndexer

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


def inject_data(count: int = 50) -> None:
    if not os.environ.get("DATABASE_URL", ""):
        raise SystemExit("DATABASE_URL is required")

    print(f"Injecting {count} dummy pages...")

    indexer = SearchIndexer()
    con = open_db()
    cur = con.cursor()

    try:
        for i in range(count):
            topic, content_base = random.choice(SAMPLE_TOPICS)
            title = topic
            content = f"{content_base} (Page {i})"

            if random.random() < 0.3:
                title = f"Article {i}"
                content = f"{topic}. {content_base}"
            elif random.random() < 0.3:
                title = f"{topic} Guide {i}"
                content = content_base

            url = f"http://example.com/page/{i}"
            indexer.index_document(url, title, content, con)

            if i > 0 and random.random() < 0.5:
                cur.execute(
                    "INSERT INTO links (src, dst) VALUES (%s, %s)",
                    (url, "http://example.com/page/0"),
                )

            for _ in range(random.randint(0, 3)):
                target_id = random.randint(0, count - 1)
                target_url = f"http://example.com/page/{target_id}"
                if target_url != url:
                    cur.execute(
                        "INSERT INTO links (src, dst) VALUES (%s, %s)",
                        (url, target_url),
                    )

        indexer.index_document(
            "http://example.com/page/0",
            "The Popular Hub Page",
            "This page is very popular. Ideally it ranks high.",
            con,
        )

        con.commit()
        print("Injection complete.")
    finally:
        cur.close()
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject dummy search data")
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()
    inject_data(count=args.count)


if __name__ == "__main__":
    main()
