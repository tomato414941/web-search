import json
import os
import sys

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from web_search.db.sqlite import open_db
from web_search.core.config import settings


def generate_dataset(output_path: str, count: int = 50):
    """
    Generate evaluation dataset by sampling random pages from the DB.
    Ref: [Title] -> Query, [URL] -> Expected Result
    """
    if not os.path.exists(settings.DB_PATH):
        print(f"Error: DB not found at {settings.DB_PATH}")
        return

    con = open_db(settings.DB_PATH)
    try:
        # Get random pages
        # Note: ORDER BY RANDOM() on large tables is slow, but fine for <100k pages.
        cur = con.execute(
            "SELECT url, title FROM pages WHERE title != '' ORDER BY RANDOM() LIMIT ?",
            (count,),
        )
        rows = cur.fetchall()

        dataset = []
        for url, title in rows:
            if not title:
                continue

            # Simple heuristic: Use the full title as the query
            # or a substring? Sticking to full title is simplest for "Known Item Search".
            dataset.append(
                {
                    "query": title.strip(),
                    "url": url,
                    "expected_urls": [url],  # List format for evaluate_search.py
                }
            )

        print(f"Generated {len(dataset)} items.")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        print(f"Saved to {output_path}")

    finally:
        con.close()


if __name__ == "__main__":
    generate_dataset("data/evaluation_set.json")
