"""Metrics module for independent calculation and slide-based ranking."""

from cable_planner.metrics.calculator import (
    calculate_length_m,
    calculate_bends,
    calculate_collinear_overlap_m,
    calculate_crossings,
    calculate_area_gap_m2,
    calculate_all_metrics,
)
from cable_planner.metrics.ranking import ranking_key, compare_solutions, is_better

__all__ = [
    "calculate_length_m",
    "calculate_bends",
    "calculate_collinear_overlap_m",
    "calculate_crossings",
    "calculate_area_gap_m2",
    "calculate_all_metrics",
    "ranking_key",
    "compare_solutions",
    "is_better",
]
