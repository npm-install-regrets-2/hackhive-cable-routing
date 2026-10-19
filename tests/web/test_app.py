"""Web boundary and slide-style export checks."""

from __future__ import annotations

import copy
from io import BytesIO
import json
import pickle
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import jsonschema
from PIL import Image
from fastapi.testclient import TestClient

from cable_planner.export import format_official_submission
from cable_planner.ingestion.normalize import NormalizationResult
from cable_planner.validation.checker import IndependentValidator
from cable_planner.web import app as web

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(web.app)


def _saved(plan_id: int) -> dict:
    return json.loads((ROOT / "examples" / "outputs" / f"kaggle_{plan_id}_combined.json").read_text(encoding="utf-8"))


def test_bundled_catalog_and_all_four_previews():
    catalog = client.get("/api/catalog").json()
    assert [item["id"] for item in catalog["presets"]] == [4944, 14433, 13033, 14926]
    assert catalog["total"] == 4
    schema = json.loads((ROOT / "shared" / "schema" / "common.schema.json").read_text(encoding="utf-8"))
    plan_validator = jsonschema.Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/plan"})
    for plan_id in (4944, 14433, 13033, 14926):
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


def test_concurrent_cold_archive_lookups_unpickle_only_once(tmp_path, monkeypatch):
    archive = tmp_path / "ResPlan.pkl"
    archive.write_bytes(pickle.dumps([{"id": 42}]))
    modified_ns = archive.stat().st_mtime_ns
    original_load = web.pickle.load
    load_count = 0
    count_lock = threading.Lock()

    def counted_load(stream):
        nonlocal load_count
        with count_lock:
            load_count += 1
        time.sleep(0.05)
        return original_load(stream)

    monkeypatch.setattr(web.pickle, "load", counted_load)
    web._cached_archive_index.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: web._trusted_archive_index(str(archive), modified_ns), range(2)
            ))
        assert results == [{42: {"id": 42}}, {42: {"id": 42}}]
        assert load_count == 1
    finally:
        web._cached_archive_index.cache_clear()


def test_unusable_local_geometry_returns_structured_diagnostics(tmp_path, monkeypatch):
    archive = tmp_path / "ResPlan.pkl"
    split = tmp_path / "split.json"
    archive.write_bytes(b"trusted fixture placeholder")
    split.write_text(json.dumps({"train": [42]}), encoding="utf-8")
    monkeypatch.setenv("RESPLAN_ARCHIVE_PATH", str(archive))
    monkeypatch.setenv("RESPLAN_SPLIT_PATH", str(split))
    monkeypatch.setattr(web, "_trusted_archive_index", lambda *_: {42: {"id": 42}})
    monkeypatch.setattr(web, "normalize_plan", lambda _raw: NormalizationResult(None, (
        {"code": "bad_geometry", "message": "Unusable boundary", "entity_ids": ["42"]},
    )))
    response = client.post("/api/runs", json={"source": "local", "plan_id": 42})
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "normalization_failed",
        "message": "Plan 42 has unusable geometry.",
        "diagnostics": [{"code": "bad_geometry", "message": "Unusable boundary", "entity_ids": ["42"]}],
    }


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


def test_streamed_run_reports_real_stages_and_preserves_sync_result(monkeypatch):
    saved = _saved(13033)

    def progress_aware_solve(_plan, *, progress_callback=None):
        if progress_callback is not None:
            progress_callback("prepare_geometry", {"eligible_rooms": 5, "legal_hub_locations": 5})
            progress_callback("search", {"hub_count_attempts": 1, "partition_patterns_examined": 24})
            progress_callback("search", {"partition_patterns_examined": 12, "ring_route_attempts": 3})
        return copy.deepcopy(saved["solution"])

    monkeypatch.setattr(web, "solve", progress_aware_solve)
    sync_response = client.post("/api/runs", json={"source": "bundled", "plan_id": 13033})
    assert sync_response.status_code == 200
    response = client.post("/api/runs/stream", json={"source": "bundled", "plan_id": 13033})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    progress_events = [event for event in events if event["type"] == "progress"]
    terminal = events[-1]
    assert terminal["type"] == "complete", terminal
    assert terminal["result"]["development"] == sync_response.json()["development"]
    assert set(terminal["result"]) == set(sync_response.json())
    last_stages = terminal["state"]["stages"]
    assert [(stage["id"], stage["status"]) for stage in last_stages] == [
        ("load_plan", "completed"), ("normalize_plan", "skipped"),
        ("prepare_geometry", "completed"), ("search", "completed"),
        ("validate", "completed"), ("render_export", "completed"),
    ]
    assert any(event["active_stage"] == "search" for event in progress_events)
    counters = terminal["state"]["counters"]
    assert counters["partition_patterns_examined"] == 36
    assert counters["ring_route_attempts"] == 3
    assert counters["eligible_rooms"] == 5
    for key in ("partition_patterns_examined", "ring_route_attempts", "candidate_combinations_evaluated"):
        observed = [event["counters"][key] for event in progress_events if key in event["counters"]]
        assert observed == sorted(observed)


def test_streamed_4944_includes_checked_side_by_side_comparison():
    response = client.post("/api/runs/stream", json={"source": "bundled", "plan_id": 4944, "compare": True})
    assert response.status_code == 200, response.text
    terminal = [json.loads(line) for line in response.text.splitlines() if line.strip()][-1]
    assert terminal["type"] == "complete", terminal
    result = terminal["result"]
    comparison = result["comparison"]
    assert (comparison["candidate_count"], comparison["qualifying_candidate_count"]) == (9, 2)
    assert comparison["criterion"] == "zero_crossings"
    assert result["validation"]["recomputed_metrics"]["route_cost"] == 45.0814
    alternative = comparison["alternative"]
    assert alternative["validation"]["is_valid"]
    assert alternative["validation"]["recomputed_metrics"]["route_cost"] == 48.4531
    assert alternative["validation"]["recomputed_metrics"]["crossings"] == 0
    assert alternative["output_image"].startswith("data:image/png;base64,")
    assert result["output_image"].startswith("data:image/png;base64,")
    assert result["submission"]["reported_metrics"]["route_cost"] == 45.081
    assert alternative["submission"]["reported_metrics"]["route_cost"] == 48.453
    schema = json.loads((ROOT / "shared/schema/common.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(result["development"])
    validator.validate(alternative["development"])


def test_comparison_without_alternative_reports_search_limit(monkeypatch):
    saved = _saved(8061)
    monkeypatch.setattr(web, "_load_plan", lambda *_args, **_kwargs: (saved["plan"], {"load_s": 0.0, "normalize_s": None}))
    result = client.post("/api/runs", json={"source": "bundled", "plan_id": 8061, "compare": True}).json()
    assert result["validation"]["is_valid"]
    assert result["comparison"]["criterion"] == "zero_crossings"
    assert result["comparison"]["candidate_count"] == 9
    assert result["comparison"]["qualifying_candidate_count"] == 0
    assert result["comparison"]["alternative"] is None


def test_streamed_solver_failure_identifies_active_stage(monkeypatch):
    def fail_during_search(_plan, *, progress_callback=None):
        if progress_callback is not None:
            progress_callback("prepare_geometry", {"eligible_rooms": 3})
            progress_callback("search", {"ring_route_attempts": 1})
        raise RuntimeError("route failed")

    monkeypatch.setattr(web, "solve", fail_during_search)
    response = client.post("/api/runs/stream", json={"source": "bundled", "plan_id": 13033})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    terminal = events[-1]
    assert terminal["type"] == "error"
    assert terminal["stage"] == "search"
    assert terminal["error"]["code"] == "solver_failed"


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
