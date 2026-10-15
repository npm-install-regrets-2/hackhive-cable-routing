"""Capacity-constrained hub placement and rectilinear cable-ring routing."""

from .thin_slice import solve as solve_thin_slice
from .grid_router import hub_count_lower_bound, solve, HananRouter, find_legal_hub_candidates

solve_grid_router = solve

__all__ = [
    "hub_count_lower_bound",
    "solve",
    "solve_thin_slice",
    "solve_grid_router",
    "HananRouter",
    "find_legal_hub_candidates",
]
