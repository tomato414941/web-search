"""Verify OpenSearch data consistency with PostgreSQL."""

import argparse
import logging
import os
import sys

from web_search_opensearch.client import INDEX_NAME, doc_id, get_client
from web_search_postgres.repositories import DocumentRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def verify(
    sample_size: int = 100,
    opensearch_url: str = "http://localhost:9200",
) -> bool:
    if not os.environ.get("DATABASE_URL", ""):
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    client = get_client(opensearch_url)
    ok = True

    pg_count = DocumentRepository.count_documents()
    opensearch_count = client.count(index=INDEX_NAME)["count"]

    logger.info("PostgreSQL documents: %d", pg_count)
    logger.info("OpenSearch documents: %d", opensearch_count)

    if pg_count != opensearch_count:
        logger.warning(
            "Count mismatch: PG=%d, OS=%d (diff=%d)",
            pg_count,
            opensearch_count,
            pg_count - opensearch_count,
        )
        ok = False
    else:
        logger.info("Document counts match")

    sample_urls = DocumentRepository.sample_document_urls(sample_size)

    missing = 0
    for url in sample_urls:
        try:
            response = client.get(index=INDEX_NAME, id=doc_id(url), ignore=[404])
            if not response.get("found"):
                missing += 1
                logger.debug("Missing in OpenSearch: %s", url)
        except Exception:
            missing += 1

    if missing > 0:
        logger.warning(
            "Sample check: %d/%d documents missing from OpenSearch",
            missing,
            len(sample_urls),
        )
        ok = False
    else:
        logger.info(
            "Sample check: all %d documents found in OpenSearch", len(sample_urls)
        )

    if ok:
        logger.info("Verification PASSED")
    else:
        logger.warning("Verification FAILED - see warnings above")

    return ok


def main():
    parser = argparse.ArgumentParser(description="Verify OpenSearch consistency")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument(
        "--opensearch-url",
        default=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
    )
    args = parser.parse_args()

    success = verify(
        sample_size=args.sample_size,
        opensearch_url=args.opensearch_url,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
