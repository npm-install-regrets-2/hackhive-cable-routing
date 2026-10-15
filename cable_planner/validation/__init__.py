"""Validation module for independent verification of floor plans and routing solutions."""

from cable_planner.validation.checker import IndependentValidator
from cable_planner.validation.models import Diagnostic, RecomputedMetrics, ValidationReport
from cable_planner.validation.rules import ValidationConfig, ELIGIBLE_ROOM_KINDS, EXCLUDED_ROOM_KINDS

__all__ = [
    "IndependentValidator",
    "Diagnostic",
    "RecomputedMetrics",
    "ValidationReport",
    "ValidationConfig",
    "ELIGIBLE_ROOM_KINDS",
    "EXCLUDED_ROOM_KINDS",
]
