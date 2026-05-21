"""Planner budget allocation for durable frontier selection."""

from __future__ import annotations

from dataclasses import dataclass

from web_search_crawler.services.crawl_policy import POLICIES

_TIER_ORDER = ("hot", "reference", "bulk")


@dataclass(frozen=True)
class FrontierTierBudget:
    tier: str
    profiles: tuple[str, ...]
    leases: int


def _group_profiles_by_budget_tier() -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for policy in POLICIES.values():
        if policy.budget_tier not in _TIER_ORDER:
            continue
        grouped.setdefault(policy.budget_tier, []).append(policy.name)
    return {
        tier: tuple(
            sorted(
                grouped.get(tier, []),
                key=lambda name: (
                    POLICIES[name].priority_bucket,
                    -POLICIES[name].priority_score_boost,
                    name,
                ),
            )
        )
        for tier in _TIER_ORDER
    }


_PROFILES_BY_TIER = _group_profiles_by_budget_tier()
_TIER_WEIGHTS = {
    tier: max(POLICIES[name].budget_weight for name in names)
    for tier, names in _PROFILES_BY_TIER.items()
    if names
}


def allocate_frontier_tier_budgets(total_leases: int) -> list[FrontierTierBudget]:
    """Allocate a crawl batch across planner tiers using simple weighted rounds."""
    if total_leases <= 0:
        return []

    active_tiers = [
        tier
        for tier in _TIER_ORDER
        if _PROFILES_BY_TIER.get(tier) and _TIER_WEIGHTS[tier] > 0
    ]
    if not active_tiers:
        return []

    lease_counts = {tier: 0 for tier in active_tiers}
    baseline = min(total_leases, len(active_tiers))
    for tier in active_tiers[:baseline]:
        lease_counts[tier] += 1

    remaining = total_leases - baseline
    if remaining > 0:
        cycle: list[str] = []
        for tier in active_tiers:
            cycle.extend([tier] * _TIER_WEIGHTS[tier])
        for index in range(remaining):
            tier = cycle[index % len(cycle)]
            lease_counts[tier] += 1

    return [
        FrontierTierBudget(
            tier=tier,
            profiles=_PROFILES_BY_TIER[tier],
            leases=lease_counts[tier],
        )
        for tier in active_tiers
        if lease_counts[tier] > 0
    ]
