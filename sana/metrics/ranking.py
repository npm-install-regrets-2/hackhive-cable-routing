"""Slide-based solution ranking and comparator."""

from typing import Tuple
from sana.metrics.models import RecomputedMetrics


def ranking_key(m: RecomputedMetrics) -> Tuple[int, float, float]:
    """
    Produce the lexicographic comparison tuple:
    1. Minimize hub count H
    2. For equal H, minimize route cost J = L + 5X + O + 0.5B
    3. For equal H and J, minimize assigned-area gap
    """
    return (m.hub_count, round(m.route_cost, 6), round(m.area_gap_m2, 6))


def compare_solutions(m1: RecomputedMetrics, m2: RecomputedMetrics) -> int:
    """
    Compare two solutions:
    Returns -1 if m1 is strictly better than m2.
    Returns 1 if m2 is strictly better than m1.
    Returns 0 if both are equivalent.
    """
    k1 = ranking_key(m1)
    k2 = ranking_key(m2)
    if k1 < k2:
        return -1
    elif k1 > k2:
        return 1
    return 0


def is_better(candidate: RecomputedMetrics, baseline: RecomputedMetrics) -> bool:
    """Check if candidate strictly ranks ahead of baseline."""
    return compare_solutions(candidate, baseline) < 0
