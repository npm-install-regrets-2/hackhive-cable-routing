"""FastAPI boundary around the trusted, independently checked planner pipeline."""

from __future__ import annotations

import base64
import io
import json
import os
import pickle
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jsonschema
import matplotlib.pyplot as plt
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cable_planner.export import format_official_submission
from cable_planner.ingestion.normalize import normalize_plan
from cable_planner.solver import solve, solve_with_comparison
from cable_planner.validation.checker import IndependentValidator
from cable_planner.visualization.renderer import render_input_plan, render_solution_overlay
from cable_planner.web.architecture import architecture_solids
from cable_planner.web.run_progress import RunProgress

ROOT = Path(__file__).resolve().parents[2]
PRESETS = (4944, 14433, 13033, 14926)
BUNDLED = ROOT / "examples" / "inputs"
SCHEMA = ROOT / "shared" / "schema" / "common.schema.json"
DIST = ROOT / "frontend" / "dist"


class RunRequest(BaseModel):
    source: Literal["bundled", "local"]
    plan_id: int
    compare: bool = False


class RunReportRequest(BaseModel):
    result: dict[str, Any]


app = FastAPI(title="Cable Ring Planner Demo")
_ARCHIVE_LOAD_LOCK = threading.Lock()


def _configured_path(variable: str, filename: str) -> Path:
    configured = os.environ.get(variable)
    if configured:
        return Path(configured).expanduser().resolve()
    for candidate in (ROOT / "archive" / filename, ROOT.parent / "archive" / filename):
        if candidate.is_file():
            return candidate.resolve()
    return (ROOT / "archive" / filename).resolve()


def _local_paths() -> tuple[Path, Path]:
    return (_configured_path("RESPLAN_ARCHIVE_PATH", "ResPlan.pkl"),
            _configured_path("RESPLAN_SPLIT_PATH", "split.json"))


def _error(status: int, code: str, message: str, diagnostics: list[dict[str, Any]] | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={
        "code": code, "message": message, "diagnostics": diagnostics or [],
    })


def _split_ids() -> dict[int, str]:
    archive, split_path = _local_paths()
    if not archive.is_file() or not split_path.is_file():
        raise _error(503, "local_dataset_unavailable", "Trusted ResPlan.pkl and split.json are required for local mode.")
    try:
        data = json.loads(split_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("split.json must contain named split arrays")
        result: dict[int, str] = {}
        for split, values in data.items():
            if not isinstance(values, list):
                raise ValueError(f"split {split} is not an array")
            for value in values:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"split {split} contains a non-integer ID")
                result.setdefault(value, split)
        return result
    except (OSError, ValueError, TypeError) as exc:
        raise _error(503, "invalid_split", f"Cannot read local split.json: {exc}") from exc


def _bundled_path(plan_id: int) -> Path:
    return BUNDLED / f"plan_{plan_id}.json"


@lru_cache(maxsize=2)
def _cached_archive_index(path: str, modified_ns: int) -> dict[int, dict[str, Any]]:
    """Index the configured trusted pickle once per file version."""
    del modified_ns
    with Path(path).open("rb") as stream:
        items = pickle.load(stream)
    if not isinstance(items, list):
        raise ValueError("ResPlan archive root must be a list")
    return {item["id"]: item for item in items if isinstance(item, dict) and isinstance(item.get("id"), int)}


def _trusted_archive_index(path: str, modified_ns: int) -> dict[int, dict[str, Any]]:
    # lru_cache is thread-safe but can execute the wrapped function more than
    # once on a concurrent cache miss. Serialize cold loads of this large file.
    with _ARCHIVE_LOAD_LOCK:
        return _cached_archive_index(path, modified_ns)


def _load_plan(
    source: str,
    plan_id: int,
    *,
    on_normalization_start: Any = None,
) -> tuple[dict[str, Any], dict[str, float | None]]:
    if source == "bundled":
        if plan_id not in PRESETS or not _bundled_path(plan_id).is_file():
            raise _error(404, "plan_not_found", f"Bundled plan {plan_id} is unavailable.")
        started = time.perf_counter()
        try:
            plan = json.loads(_bundled_path(plan_id).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _error(500, "bundled_plan_invalid", str(exc)) from exc
        return plan, {"load_s": time.perf_counter() - started, "normalize_s": None}

    if source != "local":
        raise _error(422, "invalid_source", "Source must be bundled or local.")
    if plan_id not in _split_ids():
        raise _error(404, "plan_not_in_split", f"Plan {plan_id} is not listed in split.json.")
    archive, _ = _local_paths()
    started = time.perf_counter()
    try:
        raw = _trusted_archive_index(str(archive), archive.stat().st_mtime_ns)[plan_id]
    except (OSError, KeyError, ValueError) as exc:
        raise _error(422, "plan_load_failed", str(exc)) from exc
    load_s = time.perf_counter() - started
    if on_normalization_start is not None:
        on_normalization_start()
    started = time.perf_counter()
    normalized = normalize_plan(raw)
    normalize_s = time.perf_counter() - started
    if not normalized.ok:
        raise _error(422, "normalization_failed", f"Plan {plan_id} has unusable geometry.", list(normalized.diagnostics))
    return normalized.plan, {"load_s": load_s, "normalize_s": normalize_s}


def _png_bytes(figure: plt.Figure) -> bytes:
    buffer = io.BytesIO()
    try:
        figure.savefig(buffer, format="png", bbox_inches="tight")
        return buffer.getvalue()
    finally:
        plt.close(figure)


def _png_data_uri(figure: plt.Figure) -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes(figure)).decode("ascii")


def _validate_development(document: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(document))
    if errors:
        raise _error(500, "interchange_invalid", f"Development JSON violates shared schema: {errors[0].message}")


def _checked_development(plan: dict[str, Any], solution: dict[str, Any], report: Any) -> dict[str, Any]:
    checked_solution = dict(solution)
    if report.recomputed_metrics is not None:
        checked_solution["metrics"] = report.recomputed_metrics.to_dict()
    document = {"schema_version": "0.1.0", "plan": plan, "solution": checked_solution}
    _validate_development(document)
    return document


@app.get("/api/catalog")
def catalog(source: Literal["bundled", "local"] = "bundled", q: str = "", limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
    archive, split_path = _local_paths()
    local_available = archive.is_file() and split_path.is_file()
    split_ids = _split_ids() if source == "local" else {}
    ids = sorted(split_ids) if source == "local" else list(PRESETS)
    query = q.strip()
    matches = [value for value in ids if query in str(value)] if query else ids
    return {
        "sources": ["bundled"] + (["local"] if local_available else []),
        "presets": [{"id": value, "available": value in ids, "split": split_ids.get(value)} for value in PRESETS],
        "results": [{"id": value, "split": split_ids.get(value)} for value in matches[:limit]],
        "total": len(matches),
    }


@app.get("/api/plans/{plan_id}/preview")
def preview(plan_id: int, source: Literal["bundled", "local"] = "bundled") -> Response:
    plan, _ = _load_plan(source, plan_id)
    # Use identical renderer settings to the input image returned after a run.
    return Response(
        _png_bytes(render_input_plan(plan)),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


def _execute_run(request: RunRequest, progress: RunProgress | None = None) -> dict[str, Any]:
    started_total = time.perf_counter()
    if progress is not None:
        progress.start("load_plan")

    def start_normalization() -> None:
        if progress is not None:
            progress.complete("load_plan")
            progress.start("normalize_plan")

    plan, timings = _load_plan(
        request.source,
        request.plan_id,
        on_normalization_start=(start_normalization if progress is not None and request.source == "local" else None),
    )
    if progress is not None:
        if request.source == "bundled":
            progress.complete("load_plan")
            progress.skip("normalize_plan")
        else:
            progress.complete("normalize_plan")
        progress.start("prepare_geometry")
    started = time.perf_counter()
    comparison_result = None
    try:
        if request.compare:
            comparison_result = solve_with_comparison(
                plan, progress_callback=progress.solver_update if progress is not None else None,
            )
            solution = comparison_result.selected
        else:
            solution = solve(plan, progress_callback=progress.solver_update) if progress is not None else solve(plan)
    except Exception as exc:
        raise _error(500, "solver_failed", str(exc)) from exc
    timings["solve_s"] = time.perf_counter() - started
    if progress is not None and progress.active_stage is not None:
        progress.complete(progress.active_stage)
    if progress is not None:
        progress.skip_if_upcoming("search")

    if progress is not None:
        progress.start("validate")
    started = time.perf_counter()
    try:
        report = (comparison_result.selected_report if comparison_result is not None
                  else IndependentValidator().validate(plan, solution))
    except Exception as exc:
        raise _error(500, "validation_failed", str(exc)) from exc
    timings["validate_s"] = time.perf_counter() - started

    started = time.perf_counter()
    development = _checked_development(plan, solution, report)
    checked_solution = development["solution"]
    if progress is not None:
        progress.complete("validate")
        progress.start("render_export")
    try:
        submission = (format_official_submission(plan, checked_solution, report)
                      if report.is_valid and report.recomputed_metrics is not None
                      and solution.get("status") in ("feasible", "best_known") else None)
        input_image = _png_data_uri(render_input_plan(plan))
        output_image = (_png_data_uri(render_solution_overlay(plan, checked_solution, report))
                        if solution.get("rings") else None)
        architecture = architecture_solids(plan)
        comparison = None
        if comparison_result is not None:
            comparison = {
                "criterion": comparison_result.criterion,
                "candidate_count": comparison_result.candidate_count,
                "qualifying_candidate_count": comparison_result.qualifying_candidate_count,
                "clearance_m": comparison_result.clearance_m,
                "alternative": None,
            }
            alternative = comparison_result.alternative
            alternative_report = comparison_result.alternative_report
            if alternative is not None and alternative_report is not None:
                if not alternative_report.is_valid or alternative_report.recomputed_metrics is None:
                    raise ValueError("Comparison alternative failed independent validation")
                alternative_development = _checked_development(plan, alternative, alternative_report)
                comparison["alternative"] = {
                    "validation": alternative_report.to_dict(),
                    "output_image": _png_data_uri(render_solution_overlay(
                        plan, alternative_development["solution"], alternative_report,
                    )),
                    "development": alternative_development,
                    "submission": format_official_submission(
                        plan, alternative_development["solution"], alternative_report,
                    ),
                }
    except Exception as exc:
        raise _error(500, "render_export_failed", str(exc)) from exc
    timings["render_export_s"] = time.perf_counter() - started
    timings["total_s"] = time.perf_counter() - started_total
    if progress is not None:
        progress.complete("render_export")
    return {
        "source": request.source,
        "plan_id": request.plan_id,
        "status": solution["status"],
        "lower_bound_hubs": solution.get("lower_bound_hubs"),
        "validation": report.to_dict(),
        "diagnostics": solution.get("diagnostics", []),
        "timings": {key: round(value, 4) if value is not None else None for key, value in timings.items()},
        "input_image": input_image,
        "output_image": output_image,
        "architecture": architecture,
        "development": development,
        "submission": submission,
        "comparison": comparison,
        "fallback_nodes": sum(node.get("source") == "development_fallback" for node in plan.get("nodes", [])),
    }


@app.post("/api/runs")
def run(request: RunRequest) -> dict[str, Any]:
    return _execute_run(request)


def _stream_error(exc: HTTPException) -> dict[str, Any]:
    if isinstance(exc.detail, dict):
        return exc.detail
    return {"code": "run_failed", "message": str(exc.detail), "diagnostics": []}


@app.post("/api/runs/stream")
def run_stream(request: RunRequest) -> StreamingResponse:
    progress = RunProgress()

    def execute() -> None:
        try:
            result = _execute_run(request, progress)
        except HTTPException as exc:
            progress.fail(progress.active_stage or "load_plan", _stream_error(exc))
        except Exception as exc:
            progress.fail(progress.active_stage or "load_plan", {
                "code": "run_failed", "message": str(exc), "diagnostics": [],
            })
        else:
            progress.finish(result)

    def events():
        while True:
            event = progress.next_event()
            if event is None:
                continue
            yield json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            if event["type"] in {"complete", "error"}:
                break

    threading.Thread(target=execute, name="cable-ring-run", daemon=True).start()
    return StreamingResponse(events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })


@app.post("/api/reports/pdf")
def pdf_report(request: RunReportRequest) -> Response:
    try:
        from cable_planner.web.report import build_pdf_report

        content = build_pdf_report(request.result)
    except ImportError as exc:
        raise _error(503, "pdf_dependency_unavailable", "Install the project dependencies to generate PDF reports.") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise _error(422, "invalid_report_data", str(exc)) from exc
    raw_plan_id = str(request.result.get("plan_id", "run"))
    safe_plan_id = "".join(char for char in raw_plan_id if char.isalnum() or char in "-_") or "run"
    filename = f"cable-ring-plan-{safe_plan_id}-report.pdf"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
