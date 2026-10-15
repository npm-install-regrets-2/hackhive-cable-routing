"""Streamlit demo for trusted local ResPlan smoke runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
for source_root in (ROOT, ROOT / "harshit", ROOT / "priyanshu"):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from ingestion import load_trusted_plan, normalize_plan  # noqa: E402
from sana.demo.runner import run_pipeline  # noqa: E402
from sana.export import export_solution_in_metres  # noqa: E402
from sana.visualization.renderer import render_input_plan, render_solution_overlay  # noqa: E402
from solver import SolveConfig, solve  # noqa: E402


st.set_page_config(page_title="Cable Ring Planner", layout="wide")
st.title("Closed-Ring Cable Planner")
st.caption("Trusted local ResPlan archive → normalized Plan → solver → independent validation")

archive_path = st.text_input("Trusted ResPlan archive", value=str(ROOT / "archive" / "ResPlan.pkl"))
plan_id = st.number_input("Plan ID", min_value=0, value=14433, step=1)
budget = st.number_input("Maximum assignment candidates", min_value=1, value=200, step=50)

if st.button("Run planner", type="primary"):
    try:
        raw = load_trusted_plan(archive_path, int(plan_id))
        normalized = normalize_plan(raw)
        st.subheader("Normalization")
        st.json({"ok": normalized.ok, "diagnostics": list(normalized.diagnostics)})
        if not normalized.ok:
            st.stop()

        solution = solve(normalized.plan, config=SolveConfig(max_assignment_candidates=int(budget)))
        report = run_pipeline(normalized.plan, solution)
        left, right = st.columns(2)
        with left:
            st.subheader("Solution")
            st.json(solution)
        with right:
            st.subheader("Independent validation")
            st.json(report.to_dict())

        st.subheader("Floor-plan comparison")
        st.caption("Input shows normalized rooms, fixed nodes, portals, and obstacles. Output adds the solver's assignments, hubs, and cable rings; validation metrics are recomputed independently.")
        input_col, output_col = st.columns(2)
        input_col.markdown("**Input floor plan**")
        output_col.markdown("**Solver output and checked routes**")
        input_col.pyplot(render_input_plan(normalized.plan), use_container_width=True)
        output_col.pyplot(render_solution_overlay(normalized.plan, solution, report), use_container_width=True)
        st.download_button(
            "Download provisional metre export",
            data=json.dumps(export_solution_in_metres(normalized.plan, solution), indent=2),
            file_name=f"plan-{plan_id}-metres.json",
            mime="application/json",
        )
    except Exception as error:
        st.error(f"Run failed: {error}")
