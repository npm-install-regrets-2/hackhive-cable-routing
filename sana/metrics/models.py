"""Metrics models and results representation."""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class RecomputedMetrics:
    """Independently calculated metrics from submitted geometry."""
    hub_count: int
    length_m: float
    crossings: int
    overlap_m: float
    bends: int
    route_cost: float
    area_gap_m2: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hub_count": self.hub_count,
            "length_m": round(self.length_m, 4),
            "crossings": self.crossings,
            "overlap_m": round(self.overlap_m, 4),
            "bends": self.bends,
            "route_cost": round(self.route_cost, 4),
            "area_gap_m2": round(self.area_gap_m2, 4),
        }
