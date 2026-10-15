"""Convert the development interchange geometry into metre coordinates.

The official output schema is not yet available.  This adapter intentionally
uses an explicit provisional envelope rather than presenting the development
Solution as an organizer submission.
"""

from __future__ import annotations

from typing import Any

from sana.metrics.calculator import calculate_all_metrics


def export_solution_in_metres(plan: dict[str, Any], solution: dict[str, Any]) -> dict[str, Any]:
    """Return a lower-left-origin metre-coordinate export of a checked solution."""
    scale = float(plan["drawing_units_per_metre"])
    boundary = plan["internal_boundary"]["exterior"]
    min_x = min(float(point["x"]) for point in boundary)
    min_y = min(float(point["y"]) for point in boundary)

    def point(value: dict[str, Any]) -> dict[str, float]:
        return {
            "x": (float(value["x"]) - min_x) / scale,
            "y": (float(value["y"]) - min_y) / scale,
        }

    return {
        "format": "hackhive-provisional-metre-export-v0.1",
        "plan_id": solution["plan_id"],
        "coordinate_system": {
            "unit": "metre",
            "origin": "internal_boundary_lower_left",
            "y_axis": "up",
        },
        "hubs": [
            {"id": hub["id"], "room_id": hub["room_id"], "point": point(hub["point"])}
            for hub in solution.get("hubs", [])
        ],
        "assignments": list(solution.get("assignments", [])),
        "rings": [
            {
                "hub_id": ring["hub_id"],
                "closed_sequence": list(ring["stop_ids"]),
                "route_segments": [
                    {
                        "from_id": leg["from_id"],
                        "to_id": leg["to_id"],
                        "polyline": [point(vertex) for vertex in leg["polyline"]],
                    }
                    for leg in ring["legs"]
                ],
            }
            for ring in solution.get("rings", [])
        ],
        "reported_metrics": calculate_all_metrics(plan, solution).to_dict(),
    }
