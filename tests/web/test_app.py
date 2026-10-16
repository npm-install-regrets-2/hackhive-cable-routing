"""Web boundary and slide-style export checks."""

from __future__ import annotations

import copy
from io import BytesIO
import json
from pathlib import Path

import jsonschema
import pytest
from PIL import Image
from shapely.geometry import box
from fastapi.testclient import TestClient

from cable_planner.export import format_official_submission
from cable_planner.ingestion.normalize import NormalizationResult
from cable_planner.validation.checker import IndependentValidator
from cable_planner.web import app as web

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(web.app)


def _saved(plan_id: int) -> dict:
    return json.loads((ROOT / "examples" / "outputs" / f"kaggle_{plan_id}_combined.json").read_text(encoding="utf-8"))


def test_bundled_catalog_and_all_three_previews():
    catalog = client.get("/api/catalog").json()
    assert [item["id"] for item in catalog["presets"]] == [14433, 13033, 14926]
    assert catalog["total"] == 3
    schema = json.loads((ROOT / "shared" / "schema" / "common.schema.json").read_text(encoding="utf-8"))
    plan_validator = jsonschema.Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/plan"})
    for plan_id in (14433, 13033, 14926):
        plan = json.loads((ROOT / "examples" / "inputs" / f"plan_{plan_id}.json").read_text(encoding="utf-8"))
        assert plan["id"] == str(plan_id)
        assert plan_validator.is_valid(plan)
        preview = client.get(f"/api/plans/{plan_id}/preview")
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.headers["cache-control"] == "no-store"
        assert preview.content[:8] == b"\x89PNG\r\n\x1a\n"
        preview_image = Image.open(BytesIO(preview.content))
        # Previews must use the same full-size plotting layout as post-run
        # images; the old 5x4 figure rendered at roughly 450x420 px.
        assert min(preview_image.size) >= 700
        assert preview.content == web._png_bytes(web.render_input_plan(plan))


def test_local_catalog_uses_split_and_reports_missing_dataset(tmp_path, monkeypatch):
    archive = tmp_path / "ResPlan.pkl"
    split = tmp_path / "split.json"
    archive.write_bytes(b"trusted fixture placeholder")
    split.write_text(json.dumps({"train": [14433, 14926], "test": [13033, 42]}), encoding="utf-8")
    monkeypatch.setenv("RESPLAN_ARCHIVE_PATH", str(archive))
    monkeypatch.setenv("RESPLAN_SPLIT_PATH", str(split))
    response = client.get("/api/catalog?source=local&q=149")
    assert response.status_code == 200
    assert response.json()["results"] == [{"id": 14926, "split": "train"}]
    missing = client.get("/api/plans/999/preview?source=local")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "plan_not_in_split"
    monkeypatch.setenv("RESPLAN_ARCHIVE_PATH", str(tmp_path / "absent.pkl"))
    unavailable = client.get("/api/catalog?source=local")
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "local_dataset_unavailable"


def test_unusable_local_geometry_returns_structured_diagnostics(tmp_path, monkeypatch):
    archive = tmp_path / "ResPlan.pkl"
    split = tmp_path / "split.json"
    archive.write_bytes(b"trusted fixture placeholder")
    split.write_text(json.dumps({"train": [42]}), encoding="utf-8")
    monkeypatch.setenv("RESPLAN_ARCHIVE_PATH", str(archive))
    monkeypatch.setenv("RESPLAN_SPLIT_PATH", str(split))
    monkeypatch.setattr(web, "_trusted_archive_index", lambda *_: {42: {"id": 42}})
    monkeypatch.setattr(web, "normalize_plan", lambda _raw, **_options: NormalizationResult(None, (
        {"code": "bad_geometry", "message": "Unusable boundary", "entity_ids": ["42"]},
    )))
    response = client.post("/api/runs", json={"source": "local", "plan_id": 42})
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "normalization_failed",
        "message": "Plan 42 has unusable geometry.",
        "diagnostics": [{"code": "bad_geometry", "message": "Unusable boundary", "entity_ids": ["42"]}],
    }


def test_local_plan_loader_uses_explicit_clipping_option(tmp_path, monkeypatch):
    archive = tmp_path / "ResPlan.pkl"
    split = tmp_path / "split.json"
    archive.write_bytes(b"trusted fixture placeholder")
    split.write_text(json.dumps({"train": [42]}), encoding="utf-8")
    monkeypatch.setenv("RESPLAN_ARCHIVE_PATH", str(archive))
    monkeypatch.setenv("RESPLAN_SPLIT_PATH", str(split))
    monkeypatch.setattr(web, "_trusted_archive_index", lambda *_: {42: {
        "id": 42, "inner": box(0, 0, 20, 10), "area": 50.0,
        "living": box(-2, 0, 10, 10), "bedroom": box(10, 0, 20, 10),
        "door": box(9.5, 4, 10.5, 6), "wall": None, "window": None,
    }})

    with pytest.raises(web.HTTPException) as failure:
        web._load_plan("local", 42)
    assert failure.value.status_code == 422
    assert failure.value.detail["diagnostics"][0]["code"] == "room_outside_boundary"

    plan, timings, diagnostics = web._load_plan("local", 42, clip_outside_rooms=True)
    assert plan["rooms"][0]["area_m2"] == 25
    assert diagnostics[0]["code"] == "room_clipped_to_boundary"
    assert timings["normalize_s"] is not None


def test_checked_run_exports_development_and_provisional_submission(monkeypatch):
    saved = _saved(13033)
    monkeypatch.setattr(web, "solve", lambda _plan: copy.deepcopy(saved["solution"]))
    response = client.post("/api/runs", json={"source": "bundled", "plan_id": 13033})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["validation"]["is_valid"]
    assert result["submission"]["plan_id"] == "13033"
    assert result["submission"]["units"] == "m"
    assert result["timings"]["normalize_s"] is None
    assert result["timings"]["solve_s"] >= 0
    assert result["input_image"].startswith("data:image/png;base64,")
    assert result["output_image"].startswith("data:image/png;base64,")
    assert result["architecture"]["wall_solids"]
    assert "window_solids" in result["architecture"]
    schema = json.loads((ROOT / "shared" / "schema" / "common.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(result["development"])
    assert result["development"]["solution"]["metrics"]["route_cost"] == result["validation"]["recomputed_metrics"]["route_cost"]


def test_invalid_solution_has_diagnostics_and_no_submission(monkeypatch):
    saved = _saved(13033)
    invalid = copy.deepcopy(saved["solution"])
    invalid["hubs"][0]["point"] = {"x": -10000, "y": -10000}
    monkeypatch.setattr(web, "solve", lambda _plan: invalid)
    response = client.post("/api/runs", json={"source": "bundled", "plan_id": 13033})
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result["validation"]["is_valid"]
    assert result["validation"]["violations"]
    assert result["submission"] is None


def test_slide_style_export_uses_lower_left_metre_origin_and_checked_metrics():
    for plan_id in (13033, 14433):
        saved = _saved(plan_id)
        plan, solution = saved["plan"], saved["solution"]
        report = IndependentValidator().validate(plan, solution)
        assert report.is_valid
        exported = format_official_submission(plan, solution, report)
        boundary = plan["internal_boundary"]["exterior"]
        min_x = min(point["x"] for point in boundary)
        min_y = min(point["y"] for point in boundary)
        scale = plan["drawing_units_per_metre"]
        first_hub = solution["hubs"][0]
        location = exported["hubs"][0]["location"]
        assert location == {
            "x": round((first_hub["point"]["x"] - min_x) / scale, 3),
            "y": round((first_hub["point"]["y"] - min_y) / scale, 3),
        }
        assert exported["reported_metrics"]["route_cost"] == round(report.recomputed_metrics.route_cost, 3)
        for hub in exported["hubs"]:
            assert hub["closed_sequence"][0] == hub["hub_id"] == hub["closed_sequence"][-1]
            assert abs(sum(leg["length_m"] for leg in hub["route_segments"]) - hub["ring_length_m"]) < 0.02
