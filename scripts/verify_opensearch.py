#!/usr/bin/env python3
"""Verify OpenSearch data consistency with PostgreSQL.

Usage:
    python scripts/verify_opensearch.py [--sample-size 100]

Requires:
    DATABASE_URL and OPENSEARCH_URL environment variables.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared", "src"))

from shared.opensearch.client import INDEX_NAME, get_client
from shared.postgres.search import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def verify(
    sample_size: int = 100,
    opensearch_url: str = "http://localhost:9200",
) -> bool:
    db_path = os.environ.get("DATABASE_URL", "")
    if not db_path:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    client = get_client(opensearch_url)
    conn = get_connection(db_path)
    cur = conn.cursor()
    ok = True

    # 1. Compare document counts
    cur.execute("SELECT COUNT(*) FROM documents")
    pg_count = cur.fetchone()[0]

    os_count_resp = client.count(index=INDEX_NAME)
    os_count = os_count_resp["count"]

    logger.info("PostgreSQL documents: %d", pg_count)
    logger.info("OpenSearch documents: %d", os_count)

    if pg_count != os_count:
        logger.warning(
            "Count mismatch: PG=%d, OS=%d (diff=%d)",
            pg_count,
            os_count,
            pg_count - os_count,
        )
        ok = False
    else:
        logger.info("Document counts match")

    # 2. Random sample verification
    cur.execute("SELECT url FROM documents ORDER BY random() LIMIT %s", (sample_size,))
    sample_urls = [r[0] for r in cur.fetchall()]

    missing = 0
    for url in sample_urls:
        try:
            resp = client.get(index=INDEX_NAME, id=url, ignore=[404])
            if not resp.get("found"):
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

    cur.close()
    conn.close()

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
