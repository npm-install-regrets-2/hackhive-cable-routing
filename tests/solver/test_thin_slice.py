import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from cable_planner.solver.thin_slice import hub_count_lower_bound, solve


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "three_room_plan.json"
SCHEMA = ROOT / "shared" / "schema" / "common.schema.json"


@pytest.fixture
def plan():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def validate_definition(instance, definition):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}).validate(instance)


def test_fixture_and_solution_are_schema_valid(plan):
    validate_definition(plan, "plan")
    solution = solve(plan)
    validate_definition(solution, "solution")
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(
        {"schema_version": "0.1.0", "plan": plan, "solution": solution}
    )


def test_lower_bound_and_one_connected_closed_ring(plan):
    assert hub_count_lower_bound(plan) == 1
    solution = solve(plan)
    assert solution["status"] == "feasible"
    assert solution["lower_bound_hubs"] == 1
    assert len(solution["hubs"]) == 1
    assert len(solution["assignments"]) == 3
    ring = solution["rings"][0]
    assert ring["stop_ids"][0] == ring["hub_id"] == ring["stop_ids"][-1]
    assert set(ring["stop_ids"][1:-1]) == {"node:a", "node:b", "node:c"}
    assert len(ring["legs"]) == 4
    assert all(
        a["x"] == b["x"] or a["y"] == b["y"]
        for leg in ring["legs"]
        for a, b in zip(leg["polyline"], leg["polyline"][1:])
    )


def test_both_capacity_limits_apply(plan):
    area_limited = copy.deepcopy(plan)
    area_limited["rules"]["max_area_m2_per_hub"] = 50
    assert hub_count_lower_bound(area_limited) == 2
    assert len(solve(area_limited)["hubs"]) == 3  # connected 30 m2 rooms cannot pair under 50 m2

    node_limited = copy.deepcopy(plan)
    node_limited["rules"]["max_nodes_per_hub"] = 2
    assert hub_count_lower_bound(node_limited) == 2
    assert len(solve(node_limited)["hubs"]) == 2


def test_disconnected_plan_uses_more_hubs_without_overclaiming_lower_bound(plan):
    disconnected = copy.deepcopy(plan)
    disconnected["portals"] = []
    solution = solve(disconnected)
    assert solution["status"] == "best_known"
    assert solution["lower_bound_hubs"] == 1
    assert len(solution["hubs"]) == 3
    assert solution["diagnostics"][0]["code"] == "HUB_COUNT_ABOVE_LOWER_BOUND"


def test_unsupported_geometry_is_explicit(plan):
    with_obstacle = copy.deepcopy(plan)
    with_obstacle["obstacles"] = [
        {"id": "wall:1", "kind": "wall", "geometry": [{"x": 1, "y": 1}, {"x": 1, "y": 4}]}
    ]
    solution = solve(with_obstacle)
    assert solution["status"] == "infeasible"
    assert solution["diagnostics"][0]["code"] == "UNSUPPORTED_OBSTACLES"
