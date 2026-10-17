"""The judge comparison preserves the selected route and checks alternatives."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from cable_planner.metrics.models import RecomputedMetrics
from cable_planner.solver import grid_router
from cable_planner.solver import comparison as comparison_module
from cable_planner.solver.comparison import solve_with_comparison
from cable_planner.validation.checker import IndependentValidator
from cable_planner.validation.models import ValidationReport


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Draft202012Validator(json.loads((ROOT / "shared/schema/common.schema.json").read_text()))


def bundled_plan(plan_id):
    return json.loads((ROOT / f"examples/outputs/kaggle_{plan_id}_combined.json").read_text())["plan"]


def test_4944_returns_same_selected_and_checked_zero_crossing_alternative():
    plan = bundled_plan(4944)
    baseline = grid_router.solve(plan)
    result = solve_with_comparison(plan)

    assert result.selected == baseline
    assert result.criterion == "zero_crossings"
    assert (result.candidate_count, result.qualifying_candidate_count) == (9, 2)
    assert result.alternative is not None
    assert result.selected_report.is_valid and result.alternative_report.is_valid
    for solution in (result.selected, result.alternative):
        SCHEMA.validate({"schema_version": "0.1.0", "plan": plan, "solution": solution})
        assert IndependentValidator().validate(plan, solution).is_valid
        assert len(solution["hubs"]) == solution["lower_bound_hubs"] == 2
    assert result.selected_report.recomputed_metrics.route_cost == pytest.approx(45.0814, abs=1e-4)
    alternative_metrics = result.alternative_report.recomputed_metrics
    assert alternative_metrics.crossings == 0
    assert alternative_metrics.overlap_m == 0
    assert alternative_metrics.route_cost == pytest.approx(48.4531, abs=1e-4)


def test_clean_plan_keeps_existing_solution_without_comparison():
    plan = bundled_plan(12014)
    result = solve_with_comparison(plan)
    assert result.selected == grid_router.solve(plan)
    assert result.selected_report.is_valid
    assert result.criterion is None
    assert result.alternative is None


def test_penalized_plan_without_qualifying_candidate():
    result = solve_with_comparison(bundled_plan(8061))
    assert result.selected_report.is_valid
    assert result.selected_report.recomputed_metrics.crossings > 0
    assert result.candidate_count == 9
    assert result.qualifying_candidate_count == 0
    assert result.alternative is None


def test_overlap_only_selection_chooses_zero_overlap(monkeypatch):
    plan = bundled_plan(12014)
    selected = json.loads((ROOT / "examples/outputs/kaggle_12014_combined.json").read_text())["solution"]
    alternative = copy.deepcopy(selected)
    alternative["diagnostics"][0]["code"] = "ZERO_OVERLAP_TEST"

    def fake_solve(_plan, *, cable_wall_clearance_m, candidate_observer, progress_callback=None):
        candidate_observer(copy.deepcopy(selected), cable_wall_clearance_m)
        candidate_observer(copy.deepcopy(alternative), cable_wall_clearance_m)
        return selected, cable_wall_clearance_m

    def fake_metrics(_plan, solution):
        overlap = 0 if solution["diagnostics"][0]["code"] == "ZERO_OVERLAP_TEST" else 2
        return RecomputedMetrics(1, 10, 0, overlap, 2, 11 + overlap, 0)

    def fake_validate(self, _plan, solution):
        return ValidationReport(plan_id=plan["id"], is_valid=True,
                                recomputed_metrics=fake_metrics(plan, solution))

    monkeypatch.setattr(grid_router, "_solve_observed", fake_solve)
    monkeypatch.setattr(comparison_module, "calculate_all_metrics", fake_metrics)
    monkeypatch.setattr(comparison_module.IndependentValidator, "validate", fake_validate)
    result = solve_with_comparison(plan)

    assert result.criterion == "zero_overlap"
    assert result.alternative["diagnostics"][0]["code"] == "ZERO_OVERLAP_TEST"
    assert result.qualifying_candidate_count == 1
