"""Streamlit demo for running and checking cable-planning solutions."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cable_planner.ingestion.normalize import load_trusted_plan, normalize_plan  # noqa: E402
from cable_planner.validation.checker import IndependentValidator  # noqa: E402
from cable_planner.export import format_official_submission  # noqa: E402
from cable_planner.visualization.renderer import render_input_plan, render_solution_overlay  # noqa: E402
import cable_planner.solver.grid_router as grid_router  # noqa: E402


st.set_page_config(page_title="Cable Ring Planner", layout="wide")
st.title("Closed-Ring Cable Planner")
st.caption("Normalized Plan → grid_router solver → independent validation")
solver_path = Path(grid_router.__file__).resolve()
solver_version = hashlib.sha256(solver_path.read_bytes()).hexdigest()[:12]
st.caption(f"Running solver: {solver_path} (source {solver_version})")

plan_source = st.radio(
    "Plan source",
    ("Bundled examples (cloud-ready)", "Trusted local ResPlan archive"),
    horizontal=True,
)
if plan_source == "Bundled examples (cloud-ready)":
    plan_id = st.selectbox("Example plan ID", (13033, 14433), index=0)
else:
    default_archive = ROOT.parent / "archive" / "ResPlan.pkl"
    if not default_archive.is_file():
        default_archive = ROOT / "archive" / "ResPlan.pkl"
    archive_path = st.text_input("Trusted ResPlan archive path (local only)", value=str(default_archive))
    plan_id = st.number_input("Plan ID", min_value=0, value=13033, step=1)

if st.button("Run planner", type="primary"):
    try:
        if plan_source == "Bundled examples (cloud-ready)":
            example_path = ROOT / "examples" / "outputs" / f"kaggle_{int(plan_id)}_combined.json"
            example = json.loads(example_path.read_text(encoding="utf-8"))
            plan = example["plan"]
            st.subheader("Input plan")
            st.json({"ok": True, "source": "checked-in normalized example", "plan_id": plan["id"]})
        else:
            raw = load_trusted_plan(archive_path, int(plan_id))
            normalized = normalize_plan(raw)
            st.subheader("Normalization")
            st.json({"ok": normalized.ok, "diagnostics": list(normalized.diagnostics)})
            if not normalized.ok:
                st.stop()
            plan = normalized.plan

        with st.spinner("Running grid_router optimization..."):
            # Streamlit reruns this script in one process; reload edits to the solver on every run.
            solution = importlib.reload(grid_router).solve(plan)
            validator = IndependentValidator()
            report = validator.validate(plan, solution)

        if report.recomputed_metrics is not None:
            st.metric("Checked route cost (J)", f"{report.recomputed_metrics.route_cost:.4f}")
        if report.is_valid:
            st.success("Independent validation passed")
        else:
            st.error("The independent validator rejected this solution. See the diagnostics below.")

        st.subheader("Floor-plan comparison")
        st.caption("Input shows normalized rooms, fixed nodes, portals, and obstacles. Output adds the solver's assignments, hubs, and cable rings; validation metrics are recomputed independently.")
        input_col, output_col = st.columns(2)
        input_col.markdown("**Input floor plan**")
        output_col.markdown("**Solver output and checked routes**")
        input_col.pyplot(render_input_plan(plan))
        output_col.pyplot(render_solution_overlay(plan, solution, report))

        with st.expander("Solution and independent validation details"):
            left, right = st.columns(2)
            with left:
                st.subheader("Solution")
                st.json(solution)
            with right:
                st.subheader("Independent Validation")
                st.json(report.to_dict())

        st.download_button(
            "Download Slide 8 Official Submission JSON",
            data=json.dumps(format_official_submission(plan, solution, report), indent=2),
            file_name=f"official_submission_{plan_id}.json",
            mime="application/json",
        )
    except Exception as error:
        st.error(f"Run failed: {error}")
