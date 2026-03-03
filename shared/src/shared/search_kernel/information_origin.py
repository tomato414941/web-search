"""Information Origin scoring for AI-agent-optimized ranking.

Classifies where a document sits in the information supply chain:
- Spring (1.0): Primary sources — original research, official docs, raw data
- River (0.7):  Reporting/analysis — journalism, reviews, analysis
- Delta (0.4):  Aggregation/summary — news aggregators, listicles, roundups
- Swamp (0.1):  Copies/rewrites — scraped content, thin rewrites

Key insight: PageRank says "popular = good" (River wins).
Information Origin says "primary source = good" (Spring wins).

Signal: in-link/out-link ratio.
  High inlinks + low outlinks = information supplier (Spring)
  Low inlinks + high outlinks = information consumer (Delta/Swamp)
"""

import logging
from enum import StrEnum
from typing import Any

from shared.postgres.search import open_db, sql_placeholder

logger = logging.getLogger(__name__)

_SAVE_BATCH_SIZE = 5000


class OriginType(StrEnum):
    SPRING = "spring"
    RIVER = "river"
    DELTA = "delta"
    SWAMP = "swamp"


def classify_origin(
    inlink_count: int,
    outlink_count: int,
    word_count: int,
) -> tuple[OriginType, float]:
    """Classify a document's information origin and compute score.

    Returns (origin_type, score) where score is 0.0-1.0.
    """
    # Link direction score: high inlinks + low outlinks = source
    total_links = inlink_count + outlink_count
    if total_links > 0:
        direction = inlink_count / total_links
    else:
        direction = 0.5  # unknown

    # Substance score: short pages with many outlinks = aggregator
    substance = min(1.0, word_count / 500.0) if word_count > 0 else 0.0

    # Combined score
    raw = direction * 0.7 + substance * 0.3

    if raw >= 0.7:
        return OriginType.SPRING, round(min(1.0, raw), 4)
    elif raw >= 0.45:
        return OriginType.RIVER, round(raw, 4)
    elif raw >= 0.25:
        return OriginType.DELTA, round(raw, 4)
    else:
        return OriginType.SWAMP, round(max(0.0, raw), 4)


def calculate_information_origin(db_path: str) -> int:
    """Calculate information origin scores for all documents.

    Uses the same links table as PageRank but interprets the graph
    differently: measures link direction asymmetry instead of popularity.

    Returns number of pages scored.
    """
    logger.info("Calculating information origin scores...")

    con = open_db(db_path)
    try:
        # Count inlinks per page (how many pages cite this one)
        cur = con.cursor()
        cur.execute("""
            SELECT dst AS url, COUNT(*) AS inlink_count
            FROM links
            WHERE dst IN (SELECT url FROM documents)
            GROUP BY dst
        """)
        inlinks: dict[str, int] = {}
        for url, count in cur:
            inlinks[url] = count
        cur.close()

        # Count outlinks per page (how many pages this one cites)
        cur = con.cursor()
        cur.execute("""
            SELECT src AS url, COUNT(*) AS outlink_count
            FROM links
            WHERE src IN (SELECT url FROM documents)
            GROUP BY src
        """)
        outlinks: dict[str, int] = {}
        for url, count in cur:
            outlinks[url] = count
        cur.close()

        # Get word counts
        cur = con.cursor()
        cur.execute("SELECT url, word_count FROM documents")
        word_counts: dict[str, int] = {}
        for url, wc in cur:
            word_counts[url] = wc or 0
        cur.close()

        all_urls = set(word_counts.keys())
        if not all_urls:
            logger.info("No documents found for information origin.")
            return 0

        # Classify each document
        results: list[tuple[str, str, float, int, int]] = []
        for url in all_urls:
            ic = inlinks.get(url, 0)
            oc = outlinks.get(url, 0)
            wc = word_counts.get(url, 0)
            origin_type, score = classify_origin(ic, oc, wc)
            results.append((url, origin_type, score, ic, oc))

        # Save to information_origins table
        _save_origins(con, results)

        # Log distribution
        type_counts: dict[str, int] = {}
        for _, ot, _, _, _ in results:
            type_counts[ot] = type_counts.get(ot, 0) + 1
        logger.info(
            "Information origin complete: %d pages scored. " "Distribution: %s",
            len(results),
            ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items())),
        )
        return len(results)

    finally:
        con.close()


def _save_origins(
    con: Any,
    results: list[tuple[str, str, float, int, int]],
) -> None:
    if not results:
        return
    ph = sql_placeholder()
    cur = con.cursor()
    cur.execute("DELETE FROM information_origins")
    for i in range(0, len(results), _SAVE_BATCH_SIZE):
        batch = results[i : i + _SAVE_BATCH_SIZE]
        cur.executemany(
            f"""INSERT INTO information_origins
                (url, origin_type, score, inlink_count, outlink_count)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})""",
            batch,
        )
    con.commit()
    cur.close()
