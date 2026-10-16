"""Test that visual overlay renderer generates output without errors."""

import json
from pathlib import Path
import pytest
import matplotlib.pyplot as plt

from cable_planner.validation.checker import IndependentValidator
from cable_planner.visualization.renderer import (
    _add_floorplan_legend, _add_non_overlapping_plan_labels, _shared_cable_spans,
    render_input_plan, render_solution_overlay,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
EXAMPLE_PLANS_DIR = Path(__file__).resolve().parents[2] / "examples" / "inputs"


def test_plan_13033_preview_labels_do_not_overlap():
    plan = json.loads((EXAMPLE_PLANS_DIR / "plan_13033.json").read_text(encoding="utf-8"))
    fig = render_input_plan(plan, dpi=110)
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        label_boxes = [
            text.get_window_extent(renderer)
            for axis in fig.axes
            for text in axis.texts
            if text.get_visible()
        ]
        assert all(
            not first.overlaps(second)
            for index, first in enumerate(label_boxes)
            for second in label_boxes[index + 1:]
        )
    finally:
        plt.close(fig)


def test_dense_plan_labels_are_spaced_instead_of_overlapping():
    fig, ax = plt.subplots(figsize=(12, 10), dpi=110)
    labels = [(f"room:bedroom:{index:03}", (0, 0), "room") for index in range(12)]
    _add_non_overlapping_plan_labels(ax, labels)
    renderer = fig.canvas.get_renderer()
    boxes = [text.get_window_extent(renderer) for text in ax.texts if text.get_visible()]
    assert len(boxes) == len(labels)
    assert all(
        not first.overlaps(second)
        for index, first in enumerate(boxes)
        for second in boxes[index + 1:]
    )
    plt.close(fig)


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
