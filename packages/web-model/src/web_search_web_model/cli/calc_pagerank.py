"""Calculate page-level and domain-level PageRank scores."""

import argparse
import os

from web_search_web_model.rankings import (
    calculate_domain_pagerank,
    calculate_pagerank,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate PageRank scores")
    parser.parse_args()

    if not os.environ.get("DATABASE_URL", ""):
        raise SystemExit("DATABASE_URL is required")

    print("=== Page-level PageRank ===")
    page_count = calculate_pagerank()
    print(f"Scored {page_count} pages.\n")

    print("=== Domain-level PageRank ===")
    domain_count = calculate_domain_pagerank()
    print(f"Scored {domain_count} domains.")


if __name__ == "__main__":
    main()
