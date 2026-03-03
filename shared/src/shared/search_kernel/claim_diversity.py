"""Claim Diversity — semantic clustering of search results.

Replaces domain-only diversity with content-aware clustering.
Groups results by similarity of their content, then picks the
best representative from each cluster.

AI agents read all results and integrate them. Returning 10
paraphrases of the same claim wastes 9 slots. This module
ensures each result adds unique information.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from shared.search_kernel.searcher import SearchHit

# Take first N words of content for similarity comparison
_SNIPPET_WORDS = 200


@dataclass
class ClusterMeta:
    """Per-hit cluster metadata."""

    cluster_id: int
    sources_agreeing: int


@dataclass
class DiversityResult:
    """Result of claim diversity processing."""

    hits: list[SearchHit]
    cluster_meta: dict[str, ClusterMeta]  # keyed by url
    confidence: str  # high / low / contested / none
    perspective_count: int
    total_candidates: int


def diversify_by_claims(
    hits: list[SearchHit],
    limit: int,
    similarity_threshold: float = 0.6,
    max_per_domain: int = 3,
) -> DiversityResult:
    """Cluster hits by content similarity, pick best representative per cluster.

    Args:
        hits: Score-sorted search hits (descending).
        limit: Maximum number of results to return.
        similarity_threshold: Cosine similarity above which hits are grouped.
        max_per_domain: Domain cap (applied after clustering).
    """
    if not hits:
        return DiversityResult(
            hits=[],
            cluster_meta={},
            confidence="none",
            perspective_count=0,
            total_candidates=0,
        )

    # Extract snippets for comparison
    snippets = [_extract_snippet(h.content) for h in hits]

    # Build TF-IDF vectors (lightweight, no sklearn needed)
    vectors = _tfidf_vectors(snippets)

    # Greedy clustering: assign each hit to the first cluster it's similar to
    clusters: list[list[int]] = []
    assignments: list[int] = [-1] * len(hits)

    for i in range(len(hits)):
        assigned = False
        for c_idx, cluster in enumerate(clusters):
            # Compare with cluster representative (first member)
            rep = cluster[0]
            sim = _cosine_similarity(vectors[i], vectors[rep])
            if sim >= similarity_threshold:
                cluster.append(i)
                assignments[i] = c_idx
                assigned = True
                break
        if not assigned:
            assignments[i] = len(clusters)
            clusters.append([i])

    # Pick best representative from each cluster
    # "Best" = highest composite of origin_score and factual_density
    selected: list[tuple[int, int]] = []  # (hit_index, cluster_id)
    for c_idx, cluster in enumerate(clusters):
        best_idx = max(
            cluster,
            key=lambda i: _quality_score(hits[i]),
        )
        selected.append((best_idx, c_idx))

    # Sort selected by original score (preserve relevance order)
    selected.sort(key=lambda x: hits[x[0]].score, reverse=True)

    # Apply domain cap
    from shared.search_kernel.diversify import _extract_domain

    domain_counts: dict[str, int] = {}
    final: list[tuple[int, int]] = []
    for hit_idx, c_idx in selected:
        if len(final) >= limit:
            break
        domain = _extract_domain(hits[hit_idx].url)
        count = domain_counts.get(domain, 0)
        if count >= max_per_domain:
            continue
        domain_counts[domain] = count + 1
        final.append((hit_idx, c_idx))

    # Build result
    result_hits = [hits[idx] for idx, _ in final]
    cluster_meta = {}
    for hit_idx, c_idx in final:
        cluster_meta[hits[hit_idx].url] = ClusterMeta(
            cluster_id=c_idx,
            sources_agreeing=len(clusters[c_idx]),
        )

    confidence = _compute_confidence(clusters, len(hits))
    perspective_count = len(clusters)

    return DiversityResult(
        hits=result_hits,
        cluster_meta=cluster_meta,
        confidence=confidence,
        perspective_count=perspective_count,
        total_candidates=len(hits),
    )


def _extract_snippet(content: str) -> str:
    """Take first N words for similarity comparison."""
    if not content:
        return ""
    words = content.split()[:_SNIPPET_WORDS]
    return " ".join(words).lower()


_WORD_RE = re.compile(r"\b\w{2,}\b")


def _tfidf_vectors(
    documents: list[str],
) -> list[dict[str, float]]:
    """Compute simple TF-IDF vectors without external dependencies."""
    # Tokenize
    doc_tokens: list[list[str]] = []
    for doc in documents:
        tokens = _WORD_RE.findall(doc.lower())
        doc_tokens.append(tokens)

    # Document frequency
    n = len(documents)
    df: Counter[str] = Counter()
    for tokens in doc_tokens:
        unique = set(tokens)
        for t in unique:
            df[t] += 1

    # IDF
    idf: dict[str, float] = {}
    for term, freq in df.items():
        idf[term] = math.log((n + 1) / (freq + 1)) + 1

    # TF-IDF per document
    vectors: list[dict[str, float]] = []
    for tokens in doc_tokens:
        tf: Counter[str] = Counter(tokens)
        total = len(tokens) or 1
        vec: dict[str, float] = {}
        for term, count in tf.items():
            if term in idf:
                vec[term] = (count / total) * idf[term]
        vectors.append(vec)

    return vectors


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    if not a or not b:
        return 0.0

    # Dot product (only over shared keys)
    shared_keys = set(a.keys()) & set(b.keys())
    if not shared_keys:
        return 0.0

    dot = sum(a[k] * b[k] for k in shared_keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _quality_score(hit: SearchHit) -> float:
    """Composite quality for picking cluster representative."""
    origin = hit.origin_score if hit.origin_score is not None else 0.5
    density = hit.factual_density if hit.factual_density is not None else 0.5
    return origin * 0.6 + density * 0.4


def _compute_confidence(clusters: list[list[int]], total: int) -> str:
    """Determine result-set confidence from cluster distribution."""
    if total == 0:
        return "none"

    if len(clusters) == 0:
        return "none"

    sizes = sorted([len(c) for c in clusters], reverse=True)
    largest_ratio = sizes[0] / total

    if largest_ratio >= 0.7:
        return "high"

    # Check for contested: 2+ clusters each with 20%+ share
    big_clusters = sum(1 for s in sizes if s / total >= 0.2)
    if big_clusters >= 2:
        return "contested"

    return "low"
