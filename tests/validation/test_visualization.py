"""Test that visual overlay renderer generates output without errors."""

import json
from pathlib import Path
import pytest
import matplotlib.pyplot as plt

from cable_planner.validation.checker import IndependentValidator
from cable_planner.visualization.renderer import render_solution_overlay

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
