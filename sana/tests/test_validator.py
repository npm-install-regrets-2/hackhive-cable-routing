"""Unit tests for IndependentValidator hard-rule verification and diagnostics."""

import copy
import json
from pathlib import Path
import pytest

from sana.validation.checker import IndependentValidator
from sana.validation.rules import ValidationConfig

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "fixtures"


@pytest.fixture
def canonical_fixture():
    plan_path = FIXTURES_DIR / "canonical_two_room_plan.json"
    sol_path = FIXTURES_DIR / "canonical_valid_solution.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    with open(sol_path, "r", encoding="utf-8") as f:
        sol = json.load(f)
    return plan, sol


def test_validator_canonical_valid(canonical_fixture):
    plan, sol = canonical_fixture
    validator = IndependentValidator()
    report = validator.validate(plan, sol)

    assert report.is_valid is True
    assert len(report.violations) == 0
    assert report.optimizer_metrics_match is True
    assert report.recomputed_metrics is not None
    assert pytest.approx(report.recomputed_metrics.route_cost, abs=1e-3) == 25.5


def test_validator_flags_unclosed_ring(canonical_fixture):
    plan, sol = canonical_fixture
    bad_sol = copy.deepcopy(sol)
    # Ring stops end at node_bedroom instead of hub_1
    bad_sol["rings"][0]["stop_ids"] = ["hub_1", "node_living", "node_bedroom"]
    bad_sol["rings"][0]["legs"] = bad_sol["rings"][0]["legs"][:2]

    validator = IndependentValidator()
    report = validator.validate(plan, bad_sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "RING_NOT_CLOSED" in codes or "RING_END_NOT_AT_HUB" in codes


def test_validator_flags_obstacle_collision(canonical_fixture):
    plan, sol = canonical_fixture
    bad_sol = copy.deepcopy(sol)
    # Cut through lower shared wall: (20, 25) -> (20, 10) -> (80, 10) -> (80, 25)
    # Note that (20, 10) to (80, 10) intersects wall_shared_lower at x=60, y=10
    bad_sol["rings"][0]["legs"][1]["polyline"] = [
        {"x": 20.0, "y": 25.0},
        {"x": 20.0, "y": 10.0},
        {"x": 80.0, "y": 10.0},
        {"x": 80.0, "y": 25.0},
    ]

    validator = IndependentValidator()
    report = validator.validate(plan, bad_sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "CABLE_OBSTACLE_COLLISION" in codes


def test_validator_flags_non_axis_aligned_cable(canonical_fixture):
    plan, sol = canonical_fixture
    bad_sol = copy.deepcopy(sol)
    # Introduce diagonal segment: (20, 25) directly to (80, 45)
    bad_sol["rings"][0]["legs"][1]["polyline"] = [
        {"x": 20.0, "y": 25.0},
        {"x": 80.0, "y": 45.0},
        {"x": 80.0, "y": 25.0},
    ]

    validator = IndependentValidator()
    report = validator.validate(plan, bad_sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "NON_AXIS_ALIGNED_CABLE" in codes


def test_validator_flags_unassigned_eligible_room(canonical_fixture):
    plan, sol = canonical_fixture
    bad_sol = copy.deepcopy(sol)
    # Drop room_bedroom assignment
    bad_sol["assignments"] = [bad_sol["assignments"][0]]

    validator = IndependentValidator()
    report = validator.validate(plan, bad_sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "UNASSIGNED_ELIGIBLE_ROOMS" in codes


def test_validator_flags_node_capacity_exceeded(canonical_fixture):
    plan, sol = canonical_fixture
    # Add 4 synthetic nodes to make total 6 nodes assigned to 1 hub
    bad_plan = copy.deepcopy(plan)
    bad_sol = copy.deepcopy(sol)

    for i in range(3, 7):
        r_id = f"room_extra_{i}"
        n_id = f"node_extra_{i}"
        bad_plan["rooms"].append({
            "id": r_id,
            "source_label": f"extra_{i}",
            "kind": "storage",
            "eligible": True,
            "geometry": {
                "exterior": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}, {"x": 10.0, "y": 10.0}, {"x": 0.0, "y": 10.0}, {"x": 0.0, "y": 0.0}],
                "holes": []
            },
            "area_m2": 5.0
        })
        bad_plan["nodes"].append({
            "id": n_id,
            "room_id": r_id,
            "point": {"x": 5.0, "y": 5.0},
            "source": "development_fallback"
        })
        bad_sol["assignments"].append({
            "room_id": r_id,
            "node_id": n_id,
            "hub_id": "hub_1"
        })

    validator = IndependentValidator(ValidationConfig(max_nodes_per_hub=5))
    report = validator.validate(bad_plan, bad_sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "HUB_NODE_CAPACITY_EXCEEDED" in codes


def test_validator_flags_area_capacity_exceeded(canonical_fixture):
    plan, sol = canonical_fixture
    bad_plan = copy.deepcopy(plan)
    # Increase living room area to 105 m2 (exceeding 100 m2 default)
    bad_plan["rooms"][0]["area_m2"] = 105.0

    validator = IndependentValidator()
    report = validator.validate(bad_plan, sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "HUB_AREA_CAPACITY_EXCEEDED" in codes or "ROOM_AREA_EXCEEDS_CAPACITY" in codes


def test_validator_flags_disconnected_territory(canonical_fixture):
    plan, sol = canonical_fixture
    bad_plan = copy.deepcopy(plan)
    # Remove connecting door portal so room_living and room_bedroom are not connected
    bad_plan["portals"] = []

    validator = IndependentValidator()
    report = validator.validate(bad_plan, sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "DISCONNECTED_TERRITORY" in codes


def test_validator_flags_wall_clearance_violation(canonical_fixture):
    plan, sol = canonical_fixture
    bad_plan = copy.deepcopy(plan)
    # Move node_living to (0.2, 25.0) which is 0.2 units = 0.02 m from the outer wall at x=0
    # Min clearance is 0.5 m (5.0 drawing units)
    bad_plan["nodes"][0]["point"] = {"x": 0.2, "y": 25.0}

    validator = IndependentValidator()
    report = validator.validate(bad_plan, sol)

    assert report.is_valid is False
    codes = [v.code for v in report.violations]
    assert "NODE_WALL_CLEARANCE_VIOLATION" in codes


def test_validator_detects_optimizer_metric_discrepancy(canonical_fixture):
    plan, sol = canonical_fixture
    bad_sol = copy.deepcopy(sol)
    # Falsely claim route_cost is 5.0 instead of actual 23.5
    bad_sol["metrics"]["route_cost"] = 5.0

    validator = IndependentValidator()
    report = validator.validate(plan, bad_sol)

    # Hard rules still pass, but warning is logged for claimed discrepancy
    assert report.optimizer_metrics_match is False
    warning_codes = [w.code for w in report.warnings]
    assert "CLAIMED_METRICS_DISCREPANCY" in warning_codes
