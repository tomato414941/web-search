"""Graph-derived ranking calculations."""

import logging
from urllib.parse import urlparse

from web_search_web_model.ranking_repository import RankingRepository

logger = logging.getLogger(__name__)


def calculate_pagerank(iterations: int = 20, damping: float = 0.85) -> int:
    """
    Calculate page-level PageRank and save to page_ranks table.

    Returns:
        Number of pages scored
    """
    logger.info(f"Calculating page PageRank (iter={iterations}, d={damping})...")

    nodes = RankingRepository.fetch_document_urls()
    out_links: dict[str, list[str]] = {url: [] for url in nodes}
    in_links: dict[str, list[str]] = {url: [] for url in nodes}

    for src, dst in RankingRepository.fetch_links():
        if src in nodes and dst in nodes:
            out_links[src].append(dst)
            in_links[dst].append(src)

    n = len(nodes)
    if n == 0:
        logger.info("No pages found for PageRank.")
        return 0

    scores = {url: 1.0 / n for url in nodes}
    dangling_nodes = [url for url in nodes if len(out_links[url]) == 0]
    total_edges = sum(len(destinations) for destinations in out_links.values())
    logger.info(
        f"Graph loaded: {n} nodes, {total_edges} edges, "
        f"{len(dangling_nodes)} dangling ({len(dangling_nodes) * 100 // n}%)"
    )

    for iteration in range(iterations):
        new_scores: dict[str, float] = {}
        diff = 0.0
        dangling_sum = sum(scores[url] for url in dangling_nodes)

        for url in nodes:
            incoming = 0.0
            for source in in_links[url]:
                out_degree = len(out_links[source])
                if out_degree > 0:
                    incoming += scores[source] / out_degree
            new_scores[url] = (1 - damping) / n + damping * (
                incoming + dangling_sum / n
            )

        for url in nodes:
            diff += abs(new_scores[url] - scores[url])
        scores = new_scores

        if diff < 1e-6:
            logger.info(f"Page PageRank converged at iteration {iteration + 1}.")
            break

    logger.info(f"Dangling nodes: {len(dangling_nodes)}/{n}")
    RankingRepository.replace_page_ranks(scores)
    logger.info(f"Page PageRank complete: {n} pages scored.")
    return n


def calculate_domain_pagerank(iterations: int = 20, damping: float = 0.85) -> int:
    """
    Calculate domain-level PageRank from the link graph.

    Aggregates links at the domain level (cross-domain links only)
    and runs Power Iteration on the domain graph.

    Returns:
        Number of domains scored
    """
    logger.info(f"Calculating domain PageRank (iter={iterations}, d={damping})...")

    domain_out: dict[str, set[str]] = {}
    domain_in: dict[str, set[str]] = {}
    all_domains: set[str] = set()

    for src, dst in RankingRepository.fetch_links():
        src_domain = _extract_domain(src)
        dst_domain = _extract_domain(dst)
        if not src_domain or not dst_domain:
            continue
        all_domains.add(src_domain)
        all_domains.add(dst_domain)
        if src_domain != dst_domain:
            domain_out.setdefault(src_domain, set()).add(dst_domain)
            domain_in.setdefault(dst_domain, set()).add(src_domain)

    n = len(all_domains)
    if n == 0:
        logger.info("No domains found for domain PageRank.")
        return 0

    for domain in all_domains:
        domain_out.setdefault(domain, set())
        domain_in.setdefault(domain, set())

    scores = {domain: 1.0 / n for domain in all_domains}
    dangling_domains = [
        domain for domain in all_domains if len(domain_out[domain]) == 0
    ]
    total_edges = sum(len(destinations) for destinations in domain_out.values())
    logger.info(
        f"Domain graph loaded: {n} domains, {total_edges} edges, "
        f"{len(dangling_domains)} dangling ({len(dangling_domains) * 100 // n}%)"
    )

    for iteration in range(iterations):
        new_scores: dict[str, float] = {}
        diff = 0.0
        dangling_sum = sum(scores[domain] for domain in dangling_domains)

        for domain in all_domains:
            incoming = 0.0
            for source in domain_in[domain]:
                out_degree = len(domain_out[source])
                if out_degree > 0:
                    incoming += scores[source] / out_degree
            new_scores[domain] = (1 - damping) / n + damping * (
                incoming + dangling_sum / n
            )

        for domain in all_domains:
            diff += abs(new_scores[domain] - scores[domain])
        scores = new_scores

        if diff < 1e-6:
            logger.info(f"Domain PageRank converged at iteration {iteration + 1}.")
            break

    logger.info(f"Dangling domains: {len(dangling_domains)}/{n}")
    RankingRepository.replace_domain_ranks(scores)
    logger.info(f"Domain PageRank complete: {n} domains scored.")
    return n


def _extract_domain(url: str) -> str | None:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or None
    except Exception:
        return None
