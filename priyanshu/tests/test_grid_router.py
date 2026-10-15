import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator

from solver.grid_router import hub_count_lower_bound, solve, HananRouter, find_legal_hub_candidates

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "three_room_plan.json"
SCHEMA = ROOT / "shared" / "schema" / "common.schema.json"


@pytest.fixture
def plan():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_grid_router_fixture_valid(plan):
    solution = solve(plan)
    assert solution["status"] == "feasible"
    assert solution["lower_bound_hubs"] == 1
    assert len(solution["hubs"]) == 1
    assert len(solution["rings"]) == 1
    ring = solution["rings"][0]
    assert ring["stop_ids"][0] == ring["hub_id"] == ring["stop_ids"][-1]
    assert len(ring["legs"]) == 4

    # Validate against shared schema
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(
        {"schema_version": "0.1.0", "plan": plan, "solution": solution}
    )


def test_grid_router_with_obstacle(plan):
    # Add a wall obstacle to the plan
    import copy
    with_obstacle = copy.deepcopy(plan)
    with_obstacle["obstacles"] = [
        {
            "id": "wall:1",
            "kind": "wall",
            "geometry": [{"x": 1.0, "y": 1.0}, {"x": 1.0, "y": 3.0}]
        }
    ]
    solution = solve(with_obstacle)
    assert solution["status"] == "feasible"
    assert len(solution["hubs"]) == 1
    assert len(solution["rings"]) == 1
