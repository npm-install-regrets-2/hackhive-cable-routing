"""Thin optimization and route-construction slice for normalized plans."""

from .thin_slice import hub_count_lower_bound, solve

__all__ = ["hub_count_lower_bound", "solve"]
