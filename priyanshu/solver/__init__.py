"""Optimization and route-construction slice for normalized plans."""

from .thin_slice import hub_count_lower_bound, solve as solve_thin_slice
from .grid_router import solve as solve_grid_router, HananRouter, find_legal_hub_candidates

# Default solve for backward compatibility with thin-slice tests
solve = solve_thin_slice

__all__ = [
    "hub_count_lower_bound",
    "solve",
    "solve_thin_slice",
    "solve_grid_router",
    "HananRouter",
    "find_legal_hub_candidates",
]
