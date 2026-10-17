"""Checked comparisons from complete candidates in one bounded solver run."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from jsonschema import Draft202012Validator

from cable_planner.metrics.calculator import calculate_all_metrics
from cable_planner.solver import grid_router
from cable_planner.validation.checker import IndependentValidator
from cable_planner.validation.models import ValidationReport


Criterion = Literal["zero_crossings", "zero_overlap"]
CandidateKey = tuple[float, int]


@lru_cache(maxsize=1)
def _solution_schema() -> Draft202012Validator:
    """Read the development contract when comparison runs, including installed apps."""
    relative_path = Path("shared/schema/common.schema.json")
    for root in (Path(__file__).resolve().parents[2], Path.cwd()):
        path = root / relative_path
        if path.is_file():
            return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))
    raise FileNotFoundError(f"Development schema {relative_path} is unavailable")


@dataclass(frozen=True)
class ComparisonResult:
    """Separate envelope; ``selected`` and ``alternative`` remain schema Solutions."""

    selected: Dict[str, Any]
    selected_report: ValidationReport
    alternative: Optional[Dict[str, Any]]
    alternative_report: Optional[ValidationReport]
    criterion: Optional[Criterion]
    candidate_count: int
    qualifying_candidate_count: int
    clearance_m: float


def solve_with_comparison(
    plan: Dict[str, Any], *, cable_wall_clearance_m: float = grid_router.CABLE_WALL_CLEARANCE_M,
) -> ComparisonResult:
    """Return the unchanged selected solution and its best found clean comparator.

    The observer sees each complete candidate from the existing search. Counts and
    alternatives are filtered to the selected clearance and hub count after solve.
    A candidate must pass the independent validator before it can be displayed.
    Run from the repository checkout so the shared development schema is available.
    """
    counts: dict[CandidateKey, int] = {}
    qualifying: dict[tuple[CandidateKey, Criterion], int] = {}
    best: dict[tuple[CandidateKey, Criterion], tuple[tuple[float, float], Dict[str, Any], ValidationReport]] = {}
    lower_bound = grid_router.hub_count_lower_bound(plan)

    def observe(candidate: Dict[str, Any], clearance: float) -> None:
        key = (clearance, len(candidate["hubs"]))
        counts[key] = counts.get(key, 0) + 1
        try:
            metrics = calculate_all_metrics(plan, candidate)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return
        criteria: list[Criterion] = []
        if metrics.crossings == 0:
            criteria.append("zero_crossings")
        if metrics.overlap_m <= 1e-9:
            criteria.append("zero_overlap")
        if not criteria:
            return

        rank = (metrics.route_cost, metrics.area_gap_m2)
        for criterion in criteria:
            choice = (key, criterion)
            qualifying[choice] = qualifying.get(choice, 0) + 1
            if choice in best and rank >= best[choice][0]:
                continue
            candidate["status"] = "feasible" if key[1] == lower_bound else "best_known"
            candidate["lower_bound_hubs"] = lower_bound
            if not _solution_schema().is_valid({"schema_version": "0.1.0", "plan": plan, "solution": candidate}):
                continue
            report = IndependentValidator().validate(plan, candidate)
            if report.is_valid and report.recomputed_metrics is not None:
                checked = report.recomputed_metrics
                checked_rank = (checked.route_cost, checked.area_gap_m2)
                if choice not in best or checked_rank < best[choice][0]:
                    best[choice] = (checked_rank, candidate, report)

    selected, clearance = grid_router._solve_observed(
        plan, cable_wall_clearance_m=cable_wall_clearance_m, candidate_observer=observe,
    )
    selected_report = IndependentValidator().validate(plan, selected)
    selected_metrics = selected_report.recomputed_metrics
    criterion: Optional[Criterion] = None
    if selected_report.is_valid and selected_metrics is not None:
        if selected_metrics.crossings > 0:
            criterion = "zero_crossings"
        elif selected_metrics.overlap_m > 1e-9:
            criterion = "zero_overlap"

    key = (clearance, len(selected.get("hubs", [])))
    choice = (key, criterion) if criterion is not None else None
    alternative_data = best.get(choice) if choice is not None else None
    return ComparisonResult(
        selected=selected,
        selected_report=selected_report,
        alternative=alternative_data[1] if alternative_data else None,
        alternative_report=alternative_data[2] if alternative_data else None,
        criterion=criterion,
        candidate_count=counts.get(key, 0),
        qualifying_candidate_count=qualifying.get(choice, 0) if choice else 0,
        clearance_m=clearance,
    )
