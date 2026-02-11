"""
PageRank Calculation Module

Provides both page-level and domain-level PageRank using Power Iteration.
- Page PageRank: For search result ranking (low frequency)
- Domain PageRank: For crawl priority (lightweight, higher frequency)
"""

import logging
from typing import Any
from urllib.parse import urlparse

from shared.db.search import open_db, is_postgres_mode

logger = logging.getLogger(__name__)

_SAVE_BATCH_SIZE = 5000


def _iter_batches(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _placeholder() -> str:
    return "%s" if is_postgres_mode() else "?"


def calculate_pagerank(
    db_path: str, iterations: int = 20, damping: float = 0.85
) -> int:
    """
    Calculate page-level PageRank and save to page_ranks table.

    Returns:
        Number of pages scored
    """
    logger.info(f"Calculating page PageRank (iter={iterations}, d={damping})...")

    con = open_db(db_path)
    try:
        nodes: set[str] = set()
        cur = con.cursor()
        cur.execute("SELECT url FROM documents")
        for (url,) in cur:
            nodes.add(url)
        cur.close()

        out_links: dict[str, list[str]] = {u: [] for u in nodes}
        in_links: dict[str, list[str]] = {u: [] for u in nodes}

        cur = con.cursor()
        cur.execute("SELECT src, dst FROM links")
        for src, dst in cur:
            if src in nodes and dst in nodes:
                out_links[src].append(dst)
                in_links[dst].append(src)
        cur.close()

        n = len(nodes)
        if n == 0:
            logger.info("No pages found for PageRank.")
            return 0

        scores = {u: 1.0 / n for u in nodes}
        dangling_nodes = [u for u in nodes if len(out_links[u]) == 0]
        total_edges = sum(len(v) for v in out_links.values())
        logger.info(
            f"Graph loaded: {n} nodes, {total_edges} edges, "
            f"{len(dangling_nodes)} dangling ({len(dangling_nodes) * 100 // n}%)"
        )

        for i in range(iterations):
            new_scores: dict[str, float] = {}
            diff = 0.0
            dangling_sum = sum(scores[u] for u in dangling_nodes)

            for u in nodes:
                incoming = 0.0
                for v in in_links[u]:
                    out_deg = len(out_links[v])
                    if out_deg > 0:
                        incoming += scores[v] / out_deg
                new_scores[u] = (1 - damping) / n + damping * (
                    incoming + dangling_sum / n
                )

            for u in nodes:
                diff += abs(new_scores[u] - scores[u])
            scores = new_scores

            if diff < 1e-6:
                logger.info(f"Page PageRank converged at iteration {i + 1}.")
                break

        logger.info(f"Dangling nodes: {len(dangling_nodes)}/{n}")
        _save_page_ranks(con, scores)
        logger.info(f"Page PageRank complete: {n} pages scored.")
        return n

    finally:
        con.close()


def calculate_domain_pagerank(
    db_path: str, iterations: int = 20, damping: float = 0.85
) -> int:
    """
    Calculate domain-level PageRank from the link graph.

    Aggregates links at the domain level (cross-domain links only)
    and runs Power Iteration on the domain graph.

    Returns:
        Number of domains scored
    """
    logger.info(f"Calculating domain PageRank (iter={iterations}, d={damping})...")

    con = open_db(db_path)
    try:
        # Build domain-level link graph from links table
        domain_out: dict[str, set[str]] = {}
        domain_in: dict[str, set[str]] = {}
        all_domains: set[str] = set()

        cur = con.cursor()
        cur.execute("SELECT src, dst FROM links")
        for src, dst in cur:
            src_domain = _extract_domain(src)
            dst_domain = _extract_domain(dst)
            if not src_domain or not dst_domain:
                continue
            all_domains.add(src_domain)
            all_domains.add(dst_domain)
            # Only cross-domain links
            if src_domain != dst_domain:
                domain_out.setdefault(src_domain, set()).add(dst_domain)
                domain_in.setdefault(dst_domain, set()).add(src_domain)
        cur.close()

        n = len(all_domains)
        if n == 0:
            logger.info("No domains found for domain PageRank.")
            return 0

        # Ensure all domains have entries
        for d in all_domains:
            domain_out.setdefault(d, set())
            domain_in.setdefault(d, set())

        scores = {d: 1.0 / n for d in all_domains}
        dangling_domains = [d for d in all_domains if len(domain_out[d]) == 0]
        total_edges = sum(len(v) for v in domain_out.values())
        logger.info(
            f"Domain graph loaded: {n} domains, {total_edges} edges, "
            f"{len(dangling_domains)} dangling ({len(dangling_domains) * 100 // n}%)"
        )

        for i in range(iterations):
            new_scores: dict[str, float] = {}
            diff = 0.0
            dangling_sum = sum(scores[d] for d in dangling_domains)

            for d in all_domains:
                incoming = 0.0
                for v in domain_in[d]:
                    out_deg = len(domain_out[v])
                    if out_deg > 0:
                        incoming += scores[v] / out_deg
                new_scores[d] = (1 - damping) / n + damping * (
                    incoming + dangling_sum / n
                )

            for d in all_domains:
                diff += abs(new_scores[d] - scores[d])
            scores = new_scores

            if diff < 1e-6:
                logger.info(f"Domain PageRank converged at iteration {i + 1}.")
                break

        logger.info(f"Dangling domains: {len(dangling_domains)}/{n}")
        _save_domain_ranks(con, scores)
        logger.info(f"Domain PageRank complete: {n} domains scored.")
        return n

    finally:
        con.close()


def _extract_domain(url: str) -> str | None:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or None
    except Exception:
        return None


def _save_page_ranks(con: Any, scores: dict[str, float]) -> None:
    if not scores:
        return
    max_score = max(scores.values())
    if max_score > 0:
        scores = {url: s / max_score for url, s in scores.items()}
    ph = _placeholder()
    cur = con.cursor()
    cur.execute("DELETE FROM page_ranks")
    for batch in _iter_batches(scores.items(), _SAVE_BATCH_SIZE):
        cur.executemany(
            f"INSERT INTO page_ranks (url, score) VALUES ({ph}, {ph})",
            batch,
        )
    con.commit()
    cur.close()
    logger.info(f"Saved {len(scores)} page ranks (normalized).")


def _save_domain_ranks(con: Any, scores: dict[str, float]) -> None:
    if not scores:
        return
    max_score = max(scores.values())
    if max_score > 0:
        scores = {d: s / max_score for d, s in scores.items()}
    ph = _placeholder()
    cur = con.cursor()
    cur.execute("DELETE FROM domain_ranks")
    for batch in _iter_batches(scores.items(), _SAVE_BATCH_SIZE):
        cur.executemany(
            f"INSERT INTO domain_ranks (domain, score) VALUES ({ph}, {ph})",
            batch,
        )
    con.commit()
    cur.close()
    logger.info(f"Saved {len(scores)} domain ranks (normalized).")
