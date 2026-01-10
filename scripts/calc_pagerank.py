import sys
import os

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from web_search.services.ranking import ranking_service


def main():
    ranking_service.calculate_pagerank()


if __name__ == "__main__":
    main()
