"""Test for Slide 8 official submission JSON formatting."""

import json
from pathlib import Path
from cable_planner.export import format_official_submission
from cable_planner.validation.checker import IndependentValidator

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "fixtures"


def test_format_official_submission():
    with open(FIXTURES_DIR / "canonical_two_room_plan.json") as f:
        plan = json.load(f)
    with open(FIXTURES_DIR / "canonical_valid_solution.json") as f:
        solution = json.load(f)

    validator = IndependentValidator()
    report = validator.validate(plan, solution)

    sub = format_official_submission(plan, solution, report)

    assert sub["plan_id"] == "plan_canonical_01"
    assert sub["units"] == "m"
    assert len(sub["hubs"]) == 1

    hub_0 = sub["hubs"][0]
    assert hub_0["hub_id"] == "hub_1"
    assert hub_0["location"] == {"x": 1.0, "y": 1.0}  # 10.0 units / 10.0 scale = 1.0 m
    assert hub_0["assigned_rooms"] == ["room_bedroom", "room_living"]
    assert hub_0["closed_sequence"] == ["hub_1", "node_living", "node_bedroom", "hub_1"]
    assert len(hub_0["route_segments"]) == 3
    assert hub_0["ring_length_m"] == 17.0

    assert sub["reported_metrics"]["hub_count"] == 1
    assert sub["reported_metrics"]["total_length_m"] == 17.0
    assert sub["reported_metrics"]["route_cost"] == 25.5
