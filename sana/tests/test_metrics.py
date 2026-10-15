"""Tests for independent metric calculations and slide-based ranking."""

import json
from pathlib import Path
import pytest

from sana.metrics.calculator import (
    calculate_all_metrics,
    calculate_bends,
    calculate_collinear_overlap_m,
    calculate_crossings,
    calculate_length_m,
)
from sana.metrics.ranking import compare_solutions, is_better
from sana.validation.models import RecomputedMetrics

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "fixtures"


@pytest.fixture
def canonical_plan_and_solution():
    plan_path = FIXTURES_DIR / "canonical_two_room_plan.json"
    sol_path = FIXTURES_DIR / "canonical_valid_solution.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    with open(sol_path, "r", encoding="utf-8") as f:
        sol = json.load(f)
    return plan, sol


def test_independent_metric_recomputation(canonical_plan_and_solution):
    plan, solution = canonical_plan_and_solution
    metrics = calculate_all_metrics(plan, solution)

    # Hand-checked arithmetic matches
    assert metrics.hub_count == 1
    assert pytest.approx(metrics.length_m, abs=1e-3) == 17.0
    assert metrics.crossings == 0
    assert pytest.approx(metrics.overlap_m, abs=1e-3) == 6.0
    assert metrics.bends == 5
    # J = L + 5X + O + 0.5B = 17.0 + 0 + 6.0 + 0.5*5 = 25.5
    assert pytest.approx(metrics.route_cost, abs=1e-3) == 25.5
    assert pytest.approx(metrics.area_gap_m2, abs=1e-3) == 0.0


def test_crossing_detection_with_synthetic_legs():
    # Two legs intersecting away from node or hub
    rings = [
        {
            "hub_id": "hub_1",
            "legs": [
                {
                    "from_id": "hub_1",
                    "to_id": "node_1",
                    "polyline": [{"x": 0.0, "y": 20.0}, {"x": 40.0, "y": 20.0}]
                },
                {
                    "from_id": "node_1",
                    "to_id": "hub_1",
                    "polyline": [{"x": 20.0, "y": 0.0}, {"x": 20.0, "y": 40.0}]
                }
            ]
        }
    ]
    # Crossing occurs at (20, 20). Neither node nor hub is at (20, 20)
    nodes = [{"id": "node_1", "point": {"x": 40.0, "y": 20.0}}]
    hubs = [{"id": "hub_1", "point": {"x": 0.0, "y": 20.0}}]

    crossings = calculate_crossings(rings, nodes, hubs, tol_units=0.01)
    assert crossings == 1


def test_ranking_hierarchy():
    # 1. Hub count dominance: 1 hub beats 2 hubs, even if 2 hubs has lower J
    sol_1hub = RecomputedMetrics(hub_count=1, length_m=50.0, crossings=2, overlap_m=5.0, bends=10, route_cost=70.0, area_gap_m2=0.0)
    sol_2hubs = RecomputedMetrics(hub_count=2, length_m=20.0, crossings=0, overlap_m=0.0, bends=4, route_cost=22.0, area_gap_m2=5.0)

    assert is_better(sol_1hub, sol_2hubs)
    assert not is_better(sol_2hubs, sol_1hub)

    # 2. Equal hubs: lower J beats higher J
    sol_low_j = RecomputedMetrics(hub_count=2, length_m=30.0, crossings=0, overlap_m=0.0, bends=6, route_cost=33.0, area_gap_m2=10.0)
    sol_high_j = RecomputedMetrics(hub_count=2, length_m=40.0, crossings=1, overlap_m=2.0, bends=8, route_cost=51.0, area_gap_m2=2.0)

    assert is_better(sol_low_j, sol_high_j)
    assert not is_better(sol_high_j, sol_low_j)

    # 3. Equal hubs and equal J: lower area gap breaks tie
    sol_balanced = RecomputedMetrics(hub_count=2, length_m=30.0, crossings=0, overlap_m=0.0, bends=6, route_cost=33.0, area_gap_m2=2.0)
    sol_imbalanced = RecomputedMetrics(hub_count=2, length_m=30.0, crossings=0, overlap_m=0.0, bends=6, route_cost=33.0, area_gap_m2=15.0)

    assert is_better(sol_balanced, sol_imbalanced)
    assert not is_better(sol_imbalanced, sol_balanced)
