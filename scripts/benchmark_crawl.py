import sqlite3
import time
import os
import sys

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from web_search.core.config import settings

DB_PATH = settings.DB_PATH


def get_total_indexed(db_path):
    """Get total number of indexed pages."""
    con = sqlite3.connect(db_path)
    try:
        result = con.execute("SELECT COUNT(*) FROM pages").fetchone()
        return result[0] if result else 0
    finally:
        con.close()


def main():
    print("--- Crawler Benchmark ---")
    start_time = time.time()
    start_count = get_total_indexed(DB_PATH)

    print(f"Start Count: {start_count}")
    print("Measuring for 10 seconds...")

    time.sleep(10)

    end_time = time.time()
    end_count = get_total_indexed(DB_PATH)

    duration = end_time - start_time
    processed = end_count - start_count

    print(f"End Count: {end_count}")
    print(f"Processed: {processed} pages")
    print(f"Time: {duration:.2f} seconds")
    print(f"Speed: {processed / duration:.2f} PPS (Pages Per Second)")


if __name__ == "__main__":
    main()
