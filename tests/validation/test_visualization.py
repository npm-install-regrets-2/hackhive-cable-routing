"""Test that visual overlay renderer generates output without errors."""

import json
from pathlib import Path
import pytest
import matplotlib.pyplot as plt

from cable_planner.validation.checker import IndependentValidator
from cable_planner.visualization.renderer import (
    _add_floorplan_legend, _shared_cable_spans, render_solution_overlay,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "fixtures"


def test_visual_rendering(tmp_path):
    plan_path = FIXTURES_DIR / "canonical_two_room_plan.json"
    sol_path = FIXTURES_DIR / "canonical_valid_solution.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    with open(sol_path, "r", encoding="utf-8") as f:
        sol = json.load(f)

    validator = IndependentValidator()
    report = validator.validate(plan, sol)

    out_file = tmp_path / "test_overlay.png"
    fig = render_solution_overlay(plan, sol, report, output_path=str(out_file))

    assert isinstance(fig, plt.Figure)
    assert out_file.exists()
    assert out_file.stat().st_size > 1000
    plt.close(fig)


def test_shared_span_marks_retrace_but_not_parallel_return():
    retraced = [{"legs": [
        {"polyline": [{"x": 0, "y": 0}, {"x": 3, "y": 0}]},
        {"polyline": [{"x": 3, "y": 0}, {"x": 0, "y": 0}]},
    ]}]
    parallel_return = [{"legs": [
        {"polyline": [{"x": 0, "y": 0}, {"x": 0, "y": 10}]},
        {"polyline": [{"x": 0, "y": 10}, {"x": 1, "y": 10}, {"x": 1, "y": 0}]},
    ]}]

    assert _shared_cable_spans(retraced, 1.0) == [("h", 0.0, 0.0, 3.0)]
    assert _shared_cable_spans(parallel_return, 1.0) == []


def test_open_passage_legend_identifies_free_space():
    fig, ax = plt.subplots()
    _add_floorplan_legend(ax, {
        "rooms": [], "obstacles": [],
        "portals": [{"kind": "open_passage"}],
    })
    labels = [text.get_text() for text in ax.get_legend().get_texts()]
    assert "Open Passage (free space)" in labels
    plt.close(fig)
