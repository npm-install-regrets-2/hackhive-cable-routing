"""Automated test for full 3-way integration pipeline (Harshit + Priyanshu + Sana)."""

import pytest
from shapely.geometry import box

from sana.demo.end_to_end import run_full_pipeline


def test_full_pipeline_with_raw_resplan_synthetic(tmp_path):
    raw_input = {
        "id": 101,
        "inner": box(0, 0, 20, 10),
        "area": 50.0,
        "living": box(0, 0, 10, 10),
        "bedroom": box(10, 0, 20, 10),
        "door": box(9.5, 4, 10.5, 6),
        "wall": None,
        "window": None,
    }

    render_file = str(tmp_path / "pipeline_overlay.png")
    export_file = str(tmp_path / "pipeline_combined.json")

    plan, solution, report = run_full_pipeline(
        raw_dict=raw_input,
        render_path=render_file,
        export_json_path=export_file,
    )

    assert plan is not None
    assert plan["id"] == "101"
    assert solution is not None
    assert solution["status"] == "feasible"
    assert report.is_valid is True
    assert len(report.violations) == 0
    assert report.recomputed_metrics is not None
    assert report.recomputed_metrics.hub_count == 1
    assert (tmp_path / "pipeline_overlay.png").exists()
    assert (tmp_path / "pipeline_combined.json").exists()
