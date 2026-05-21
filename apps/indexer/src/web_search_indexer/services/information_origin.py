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

from web_search_postgres.repositories import RankingRepository

logger = logging.getLogger(__name__)


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
    total_links = inlink_count + outlink_count
    if total_links > 0:
        direction = inlink_count / total_links
    else:
        direction = 0.5

    substance = min(1.0, word_count / 500.0) if word_count > 0 else 0.0
    raw = direction * 0.7 + substance * 0.3

    if raw >= 0.7:
        return OriginType.SPRING, round(min(1.0, raw), 4)
    if raw >= 0.45:
        return OriginType.RIVER, round(raw, 4)
    if raw >= 0.25:
        return OriginType.DELTA, round(raw, 4)
    return OriginType.SWAMP, round(max(0.0, raw), 4)


def calculate_information_origin() -> int:
    """Calculate information origin scores for all documents.

    Uses the same links table as PageRank but interprets the graph
    differently: measures link direction asymmetry instead of popularity.

    Returns number of pages scored.
    """
    logger.info("Calculating information origin scores...")

    inlinks = RankingRepository.fetch_inlink_counts()
    outlinks = RankingRepository.fetch_outlink_counts()
    word_counts = RankingRepository.fetch_document_word_counts()

    all_urls = set(word_counts.keys())
    if not all_urls:
        logger.info("No documents found for information origin.")
        return 0

    results: list[tuple[str, str, float, int, int]] = []
    for url in all_urls:
        inlink_count = inlinks.get(url, 0)
        outlink_count = outlinks.get(url, 0)
        word_count = word_counts.get(url, 0)
        origin_type, score = classify_origin(inlink_count, outlink_count, word_count)
        results.append((url, origin_type, score, inlink_count, outlink_count))

    RankingRepository.replace_information_origins(results)

    type_counts: dict[str, int] = {}
    for _, origin_type, _, _, _ in results:
        type_counts[origin_type] = type_counts.get(origin_type, 0) + 1
    logger.info(
        "Information origin complete: %d pages scored. Distribution: %s",
        len(results),
        ", ".join(f"{key}={value}" for key, value in sorted(type_counts.items())),
    )
    return len(results)
