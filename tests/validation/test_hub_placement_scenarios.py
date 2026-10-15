"""Comprehensive test scenarios for hub placement, capacity bounds, and hard rules.

Tests:
1. Area-forced multi-hub placement (Total area > 100 m2).
2. Node-forced multi-hub placement (Node count > 5).
3. Disconnection-forced multi-hub placement (Disconnected room components).
4. Hub placement legality checks (No hubs in excluded rooms, hubs must be inside assigned territory).
5. Configurable capacity check (5-node vs 20-node limit).
"""

import copy
import json
from pathlib import Path
import pytest
from shapely.geometry import Point, box

from cable_planner.validation.checker import IndependentValidator
from cable_planner.validation.rules import ValidationConfig
from cable_planner.demo.end_to_end import run_full_pipeline

# Exercise the legacy thin solver explicitly for placement scenarios.
from cable_planner.solver.thin_slice import solve, hub_count_lower_bound


def make_box_poly(x1, y1, x2, y2):
    return {
        "exterior": [
            {"x": float(x1), "y": float(y1)},
            {"x": float(x2), "y": float(y1)},
            {"x": float(x2), "y": float(y2)},
            {"x": float(x1), "y": float(y2)},
            {"x": float(x1), "y": float(y1)},
        ],
        "holes": [],
    }


def test_area_forces_two_hubs():
    """Scenario 1: Total area = 120 m2 (> 100 m2) forces at least 2 hubs."""
    plan = {
        "id": "plan_area_120m2",
        "drawing_units_per_metre": 1.0,
        "internal_boundary": make_box_poly(0, 0, 30, 5),
        "rooms": [
            {"id": "room:1", "source_label": "living_0", "kind": "living", "eligible": True, "geometry": make_box_poly(0, 0, 15, 5), "area_m2": 60.0},
            {"id": "room:2", "source_label": "bedroom_0", "kind": "bedroom", "eligible": True, "geometry": make_box_poly(15, 0, 30, 5), "area_m2": 60.0},
        ],
        "nodes": [
            {"id": "node:1", "room_id": "room:1", "point": {"x": 5.0, "y": 2.5}, "source": "development_fallback"},
            {"id": "node:2", "room_id": "room:2", "point": {"x": 20.0, "y": 2.5}, "source": "development_fallback"},
        ],
        "portals": [
            {"id": "portal:12", "space_a_id": "room:1", "space_b_id": "room:2", "kind": "door", "segment": [{"x": 15.0, "y": 2.0}, {"x": 15.0, "y": 3.0}]}
        ],
        "obstacles": [],
        "rules": {"max_area_m2_per_hub": 100.0, "max_nodes_per_hub": 5, "node_wall_clearance_m": 0.5, "geometry_tolerance": 0.001},
    }

    # Arithmetic lower bound must be ceil(120 / 100) = 2 hubs
    lb = hub_count_lower_bound(plan)
    assert lb == 2

    # Solver must open 2 hubs
    solution = solve(plan)
    assert solution["status"] == "feasible"
    assert len(solution["hubs"]) == 2

    # Validator must independently confirm zero violations
    validator = IndependentValidator()
    report = validator.validate(plan, solution)
    assert report.is_valid is True
    assert len(report.violations) == 0
    assert report.recomputed_metrics.hub_count == 2


def test_node_count_forces_two_hubs():
    """Scenario 2: 6 small rooms (60 m2 total <= 100 m2) force 2 hubs because 6 nodes > 5 nodes."""
    rooms = []
    nodes = []
    portals = []
    for i in range(6):
        r_id = f"room:{i}"
        n_id = f"node:{i}"
        rooms.append({
            "id": r_id,
            "source_label": f"room_{i}",
            "kind": "bedroom" if i % 2 == 0 else "living",
            "eligible": True,
            "geometry": make_box_poly(i * 3, 0, (i + 1) * 3, 3),
            "area_m2": 9.0,  # 6 * 9 = 54 m2 (< 100 m2)
        })
        nodes.append({
            "id": n_id,
            "room_id": r_id,
            "point": {"x": i * 3 + 1.5, "y": 1.5},
            "source": "development_fallback",
        })
        if i > 0:
            portals.append({
                "id": f"portal:{i-1}_{i}",
                "space_a_id": f"room:{i-1}",
                "space_b_id": r_id,
                "kind": "door",
                "segment": [{"x": float(i * 3), "y": 1.0}, {"x": float(i * 3), "y": 2.0}],
            })

    plan = {
        "id": "plan_6_nodes",
        "drawing_units_per_metre": 1.0,
        "internal_boundary": make_box_poly(0, 0, 18, 3),
        "rooms": rooms,
        "nodes": nodes,
        "portals": portals,
        "obstacles": [],
        "rules": {"max_area_m2_per_hub": 100.0, "max_nodes_per_hub": 5, "node_wall_clearance_m": 0.5, "geometry_tolerance": 0.001},
    }

    # Lower bound must be ceil(6 / 5) = 2 hubs
    lb = hub_count_lower_bound(plan)
    assert lb == 2

    # Solver must open 2 hubs
    solution = solve(plan)
    assert solution["status"] == "feasible"
    assert len(solution["hubs"]) == 2

    # Validator must confirm both hubs own <= 5 nodes
    validator = IndependentValidator()
    report = validator.validate(plan, solution)
    assert report.is_valid is True
    assert report.recomputed_metrics.hub_count == 2


def test_disconnected_rooms_force_two_hubs():
    """Scenario 3: Two rooms with NO connecting portal force 2 hubs for territory connectivity."""
    plan = {
        "id": "plan_disconnected",
        "drawing_units_per_metre": 1.0,
        "internal_boundary": make_box_poly(0, 0, 20, 5),
        "rooms": [
            {"id": "room:east", "source_label": "living_0", "kind": "living", "eligible": True, "geometry": make_box_poly(0, 0, 10, 5), "area_m2": 25.0},
            {"id": "room:west", "source_label": "bedroom_0", "kind": "bedroom", "eligible": True, "geometry": make_box_poly(10, 0, 20, 5), "area_m2": 25.0},
        ],
        "nodes": [
            {"id": "node:east", "room_id": "room:east", "point": {"x": 5.0, "y": 2.5}, "source": "development_fallback"},
            {"id": "node:west", "room_id": "room:west", "point": {"x": 15.0, "y": 2.5}, "source": "development_fallback"},
        ],
        "portals": [],  # NO DOOR between east and west!
        "obstacles": [],
        "rules": {"max_area_m2_per_hub": 100.0, "max_nodes_per_hub": 5, "node_wall_clearance_m": 0.5, "geometry_tolerance": 0.001},
    }

    # Arithmetic lower bound is 1, BUT 1 hub would have disconnected territory
    assert hub_count_lower_bound(plan) == 1

    solution = solve(plan)
    # Solver must open 2 hubs (best_known above arithmetic lower bound) to keep territories connected
    assert solution["status"] == "best_known"
    assert len(solution["hubs"]) == 2

    # Validator verifies that each hub owns exactly 1 room and territories are fully connected
    validator = IndependentValidator()
    report = validator.validate(plan, solution)
    assert report.is_valid is True


def test_validator_rejects_hub_in_excluded_room():
    """Scenario 4: Validator strictly rejects any hub placed in a bathroom or balcony."""
    plan = {
        "id": "plan_with_bathroom",
        "drawing_units_per_metre": 1.0,
        "internal_boundary": make_box_poly(0, 0, 20, 10),
        "rooms": [
            {"id": "room:living", "source_label": "living_0", "kind": "living", "eligible": True, "geometry": make_box_poly(0, 0, 10, 10), "area_m2": 40.0},
            {"id": "room:bath", "source_label": "bath_0", "kind": "bathroom", "eligible": False, "geometry": make_box_poly(10, 0, 20, 10), "area_m2": 10.0},
        ],
        "nodes": [
            {"id": "node:living", "room_id": "room:living", "point": {"x": 5.0, "y": 5.0}, "source": "development_fallback"},
        ],
        "portals": [],
        "obstacles": [],
        "rules": {"max_area_m2_per_hub": 100.0, "max_nodes_per_hub": 5, "node_wall_clearance_m": 0.5, "geometry_tolerance": 0.001},
    }

    # Illegally place hub inside the bathroom
    illegal_solution = {
        "plan_id": "plan_with_bathroom",
        "status": "feasible",
        "lower_bound_hubs": 1,
        "hubs": [
            {"id": "hub:1", "point": {"x": 15.0, "y": 5.0}, "room_id": "room:bath"}
        ],
        "assignments": [
            {"room_id": "room:living", "node_id": "node:living", "hub_id": "hub:1"}
        ],
        "rings": [
            {
                "hub_id": "hub:1",
                "stop_ids": ["hub:1", "node:living", "hub:1"],
                "legs": [
                    {"from_id": "hub:1", "to_id": "node:living", "polyline": [{"x": 15.0, "y": 5.0}, {"x": 5.0, "y": 5.0}]},
                    {"from_id": "node:living", "to_id": "hub:1", "polyline": [{"x": 5.0, "y": 5.0}, {"x": 15.0, "y": 5.0}]},
                ],
            }
        ],
        "diagnostics": [],
    }

    validator = IndependentValidator()
    report = validator.validate(plan, illegal_solution)
    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "HUB_IN_EXCLUDED_ROOM" in codes


def test_configurable_node_capacity_20_vs_5():
    """Scenario 5: 6 nodes under 5-node capacity requires 2 hubs; under 20-node capacity requires only 1 hub."""
    rooms = []
    nodes = []
    for i in range(6):
        r_id = f"room:{i}"
        rooms.append({"id": r_id, "source_label": f"r_{i}", "kind": "living", "eligible": True, "geometry": make_box_poly(i*2, 0, (i+1)*2, 2), "area_m2": 4.0})
        nodes.append({"id": f"node:{i}", "room_id": r_id, "point": {"x": i*2 + 1.0, "y": 1.0}, "source": "development_fallback"})

    # Under 5-node capacity:
    plan_cap5 = {
        "id": "cap5", "drawing_units_per_metre": 1.0, "internal_boundary": make_box_poly(0, 0, 12, 2),
        "rooms": rooms, "nodes": nodes, "portals": [], "obstacles": [],
        "rules": {"max_area_m2_per_hub": 100.0, "max_nodes_per_hub": 5, "node_wall_clearance_m": 0.5, "geometry_tolerance": 0.001}
    }
    assert hub_count_lower_bound(plan_cap5) == 2

    # Under older 20-node capacity:
    plan_cap20 = {
        "id": "cap20", "drawing_units_per_metre": 1.0, "internal_boundary": make_box_poly(0, 0, 12, 2),
        "rooms": rooms, "nodes": nodes, "portals": [], "obstacles": [],
        "rules": {"max_area_m2_per_hub": 100.0, "max_nodes_per_hub": 20, "node_wall_clearance_m": 0.5, "geometry_tolerance": 0.001}
    }
    assert hub_count_lower_bound(plan_cap20) == 1
