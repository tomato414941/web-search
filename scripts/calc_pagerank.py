#!/usr/bin/env python3
"""
Calculate PageRank scores (page-level and domain-level).

Usage:
    python scripts/calc_pagerank.py [--db-path /path/to/search.db]
"""

import argparse
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.pagerank import calculate_pagerank, calculate_domain_pagerank
from shared.core.infrastructure_config import settings


def main():
    parser = argparse.ArgumentParser(description="Calculate PageRank scores")
    parser.add_argument(
        "--db-path", default=settings.DB_PATH, help="Path to search database"
    )
    args = parser.parse_args()

    print("=== Page-level PageRank ===")
    page_count = calculate_pagerank(args.db_path)
    print(f"Scored {page_count} pages.\n")

    print("=== Domain-level PageRank ===")
    domain_count = calculate_domain_pagerank(args.db_path)
    print(f"Scored {domain_count} domains.")


if __name__ == "__main__":
    main()
