"""Export solutions to the official Slide 8 Submission JSON format."""

import math
from typing import Any, Dict, List, Optional
from cable_planner.validation.models import ValidationReport
from cable_planner.metrics.calculator import calculate_all_metrics


def format_official_submission(
    plan: Dict[str, Any],
    solution: Dict[str, Any],
    report: Optional[ValidationReport] = None,
) -> Dict[str, Any]:
    """
    Format output matching Slide 8 of the challenge deck:
    - Coordinates converted to physical metres after subtracting the internal
      boundary's lower-left drawing-unit origin; y remains upward.
    - Structure:
        {
          "plan_id": "...",
          "units": "m",
          "hubs": [
            {
              "hub_id": "H1",
              "room_id": "...",
              "location": {"x": 5.2, "y": 3.6},
              "assigned_rooms": ["...", ...],
              "assigned_nodes": ["...", ...],
              "closed_sequence": ["H1", "N1", ...],
              "route_segments": [
                {"from": "H1", "to": "N1", "length_m": 4.8, "polyline": [[x, y], ...]}
              ],
              "ring_length_m": 23.8
            }
          ],
          "reported_metrics": {
            "hub_count": 2,
            "total_length_m": 49.0,
            "crossings": 0,
            "overlap_m": 0.0,
            "bends": 8,
            "route_cost": 53.0
          }
        }
    """
    scale = float(plan["drawing_units_per_metre"])
    boundary = plan["internal_boundary"]["exterior"]
    origin_x = min(float(vertex["x"]) for vertex in boundary)
    origin_y = min(float(vertex["y"]) for vertex in boundary)

    def metre_point(value: Dict[str, Any]) -> tuple[float, float]:
        return ((float(value["x"]) - origin_x) / scale,
                (float(value["y"]) - origin_y) / scale)

    # Map assignments by hub
    hub_assigned_rooms: Dict[str, List[str]] = {}
    hub_assigned_nodes: Dict[str, List[str]] = {}
    for a in solution.get("assignments", []):
        h_id = a.get("hub_id")
        r_id = a.get("room_id")
        n_id = a.get("node_id")
        if h_id:
            if r_id:
                hub_assigned_rooms.setdefault(h_id, []).append(r_id)
            if n_id:
                hub_assigned_nodes.setdefault(h_id, []).append(n_id)

    # Map rings by hub
    rings_by_hub: Dict[str, Dict[str, Any]] = {
        r.get("hub_id"): r for r in solution.get("rings", [])
    }

    hubs_output: List[Dict[str, Any]] = []
    total_length_m = 0.0

    for hub in solution.get("hubs", []):
        h_id = hub.get("id")
        hx_m, hy_m = (round(value, 3) for value in metre_point(hub["point"]))

        ring = rings_by_hub.get(h_id, {})
        stop_ids = ring.get("stop_ids", [])
        legs = ring.get("legs", [])

        route_segments = []
        ring_length_units = 0.0

        for leg in legs:
            from_id = leg.get("from_id")
            to_id = leg.get("to_id")
            poly_units = leg.get("polyline", [])

            leg_len_units = 0.0
            polyline_m = []
            for i in range(len(poly_units)):
                px = float(poly_units[i]["x"])
                py = float(poly_units[i]["y"])
                mx, my = metre_point(poly_units[i])
                polyline_m.append([round(mx, 3), round(my, 3)])
                if i > 0:
                    prev_x = float(poly_units[i - 1]["x"])
                    prev_y = float(poly_units[i - 1]["y"])
                    leg_len_units += math.hypot(px - prev_x, py - prev_y)

            leg_len_m = round(leg_len_units / scale, 3)
            ring_length_units += leg_len_units

            route_segments.append({
                "from": from_id,
                "to": to_id,
                "length_m": leg_len_m,
                "polyline": polyline_m,
            })

        ring_len_m = round(ring_length_units / scale, 3)
        total_length_m += ring_len_m

        hubs_output.append({
            "hub_id": h_id,
            "room_id": hub.get("room_id"),
            "location": {"x": hx_m, "y": hy_m},
            "assigned_rooms": sorted(list(set(hub_assigned_rooms.get(h_id, [])))),
            "assigned_nodes": sorted(list(set(hub_assigned_nodes.get(h_id, [])))),
            "closed_sequence": stop_ids,
            "route_segments": route_segments,
            "ring_length_m": ring_len_m,
        })

    # Reported metrics: use validator's verified metrics if available
    if report and report.recomputed_metrics:
        m = report.recomputed_metrics
        reported_metrics = {
            "hub_count": m.hub_count,
            "total_length_m": round(m.length_m, 3),
            "crossings": m.crossings,
            "overlap_m": round(m.overlap_m, 3),
            "bends": m.bends,
            "route_cost": round(m.route_cost, 3),
            "area_gap_m2": round(m.area_gap_m2, 3),
        }
    else:
        reported_metrics = {
            "hub_count": len(solution.get("hubs", [])),
            "total_length_m": round(total_length_m, 3),
        }

    return {
        "plan_id": str(plan.get("id")),
        "units": "m",
        "hubs": hubs_output,
        "reported_metrics": reported_metrics,
    }


def export_solution_in_metres(plan: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    """Return the earlier provisional metre export with a lower-left origin."""
    scale = float(plan["drawing_units_per_metre"])
    boundary = plan["internal_boundary"]["exterior"]
    min_x = min(float(point["x"]) for point in boundary)
    min_y = min(float(point["y"]) for point in boundary)

    def point(value: Dict[str, Any]) -> Dict[str, float]:
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
