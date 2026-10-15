"""Rule configuration, tolerances, and eligible domain types."""

from dataclasses import dataclass
from typing import Set

# Canonical eligible and excluded room types per CONTEXT.md
ELIGIBLE_ROOM_KINDS: Set[str] = {"living", "bedroom", "kitchen", "storage"}
EXCLUDED_ROOM_KINDS: Set[str] = {
    "bathroom", "balcony", "stair", "garden", "pool", "parking", "land"
}

# Default constraints
DEFAULT_MAX_AREA_M2_PER_HUB: float = 100.0
DEFAULT_MAX_NODES_PER_HUB: int = 5
DEFAULT_NODE_WALL_CLEARANCE_M: float = 0.5
DEFAULT_GEOMETRY_TOLERANCE_M: float = 0.001  # 1 mm


@dataclass
class ValidationConfig:
    """Configurable constraints and tolerances for validation and scoring."""
    max_area_m2_per_hub: float = DEFAULT_MAX_AREA_M2_PER_HUB
    max_nodes_per_hub: int = DEFAULT_MAX_NODES_PER_HUB
    node_wall_clearance_m: float = DEFAULT_NODE_WALL_CLEARANCE_M
    geometry_tolerance_m: float = DEFAULT_GEOMETRY_TOLERANCE_M
    allow_window_transitions: bool = False  # Hard rule: windows are never traversable

    @classmethod
    def from_plan_rules(cls, rules_dict: dict, drawing_units_per_metre: float = 1.0) -> "ValidationConfig":
        """Build config from the plan's declared rules with defaults."""
        return cls(
            max_area_m2_per_hub=float(rules_dict.get("max_area_m2_per_hub", DEFAULT_MAX_AREA_M2_PER_HUB)),
            max_nodes_per_hub=int(rules_dict.get("max_nodes_per_hub", DEFAULT_MAX_NODES_PER_HUB)),
            node_wall_clearance_m=float(rules_dict.get("node_wall_clearance_m", DEFAULT_NODE_WALL_CLEARANCE_M)),
            geometry_tolerance_m=float(rules_dict.get("geometry_tolerance", DEFAULT_GEOMETRY_TOLERANCE_M)),
        )
