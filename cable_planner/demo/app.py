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
from cable_planner.export import format_official_submission  # noqa: E402
from cable_planner.demo.environment import available_plan_sources  # noqa: E402
from cable_planner.visualization.renderer import render_input_plan, render_solution_overlay  # noqa: E402
from cable_planner.solver.comparison import solve_with_comparison  # noqa: E402
import cable_planner.solver.grid_router as grid_router  # noqa: E402


st.set_page_config(page_title="Cable Ring Planner", layout="wide")
st.title("Closed-Ring Cable Planner")
st.caption("Normalized Plan → grid_router solver → independent validation")
solver_path = Path(grid_router.__file__).resolve()
solver_version = hashlib.sha256(solver_path.read_bytes()).hexdigest()[:12]
st.caption(f"Running solver: {solver_path} (source {solver_version})")

plan_sources = available_plan_sources(st.context.url)
if len(plan_sources) == 1:
    st.info(
        "This hosted app can use the bundled examples only. It cannot read files from your computer. "
        "To use a local ResPlan archive, run the app on the same machine that can access that file."
    )
    plan_source = plan_sources[0]
else:
    plan_source = st.radio(
        "Plan source",
        plan_sources,
        horizontal=True,
    )
if plan_source == "Bundled examples (cloud-ready)":
    plan_id = st.selectbox("Example plan ID", (12014, 8063, 4944, 8061, 13033, 14433), index=0)
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
            importlib.reload(grid_router)
            comparison = solve_with_comparison(plan)
            solution = comparison.selected
            report = comparison.selected_report

        if report.recomputed_metrics is not None:
            hub_col, cost_col = st.columns(2)
            hub_col.metric("Hubs / lower bound", f"{len(solution['hubs'])} / {solution.get('lower_bound_hubs', '?')}")
            cost_col.metric("Checked route cost (J)", f"{report.recomputed_metrics.route_cost:.4f}")
            st.caption("Matching the lower bound proves the minimum hub count under the configured rules. The route cost is checked, but a global minimum is not proven.")
        if report.is_valid:
            st.success("Independent validation passed")
        else:
            st.error("The independent validator rejected this solution. See the diagnostics below.")

        st.subheader("Floor-plan comparison")
        if comparison.criterion is not None and comparison.alternative is not None:
            alternative = comparison.alternative
            alternative_report = comparison.alternative_report
            assert alternative_report is not None and alternative_report.recomputed_metrics is not None
            selected_metrics = report.recomputed_metrics
            alternative_metrics = alternative_report.recomputed_metrics
            assert selected_metrics is not None
            criterion_name = "zero crossings" if comparison.criterion == "zero_crossings" else "zero overlap"
            st.caption(
                f"Best found within the bounded search at {comparison.clearance_m:g} m cable clearance. "
                f"{comparison.qualifying_candidate_count} of {comparison.candidate_count} generated complete "
                f"candidates had {criterion_name}. Both use {len(solution['hubs'])} hubs; "
                "hub positions and territory assignments may differ. A global minimum J is not proven."
            )
            selected_col, alternative_col = st.columns(2)
            selected_col.markdown("**Selected best found route**")
            alternative_col.markdown(f"**Best found {criterion_name} route**")
            selected_col.pyplot(render_solution_overlay(plan, solution, report))
            alternative_col.pyplot(render_solution_overlay(plan, alternative, alternative_report))
            st.table({
                "Metric": ["H", "L (m)", "X", "O (m)", "B", "J", "Area gap (m²)"],
                "Selected": [selected_metrics.hub_count, round(selected_metrics.length_m, 4),
                             selected_metrics.crossings, round(selected_metrics.overlap_m, 4),
                             selected_metrics.bends, round(selected_metrics.route_cost, 4),
                             round(selected_metrics.area_gap_m2, 4)],
                "Alternative": [alternative_metrics.hub_count, round(alternative_metrics.length_m, 4),
                                alternative_metrics.crossings, round(alternative_metrics.overlap_m, 4),
                                alternative_metrics.bends, round(alternative_metrics.route_cost, 4),
                                round(alternative_metrics.area_gap_m2, 4)],
            })
            st.metric("Alternative J minus selected J", f"{alternative_metrics.route_cost - selected_metrics.route_cost:+.4f}")
            with st.expander("Input floor plan"):
                st.pyplot(render_input_plan(plan))
            download_col, alternative_download_col = st.columns(2)
            download_col.download_button(
                "Download selected checked JSON",
                data=json.dumps(format_official_submission(plan, solution, report), indent=2),
                file_name=f"official_submission_{plan_id}_selected.json",
                mime="application/json",
            )
            alternative_download_col.download_button(
                "Download alternative checked JSON",
                data=json.dumps(format_official_submission(plan, alternative, alternative_report), indent=2),
                file_name=f"official_submission_{plan_id}_alternative.json",
                mime="application/json",
            )
        else:
            st.caption("Input shows normalized rooms, fixed nodes, portals, and obstacles. Output adds the solver's assignments, hubs, and cable rings; validation metrics are recomputed independently.")
            input_col, output_col = st.columns(2)
            input_col.markdown("**Input floor plan**")
            output_col.markdown("**Solver output and checked routes**")
            input_col.pyplot(render_input_plan(plan))
            output_col.pyplot(render_solution_overlay(plan, solution, report))
            if comparison.criterion is not None:
                st.info("No qualifying candidate found in this search")

        with st.expander("Solution and independent validation details"):
            left, right = st.columns(2)
            with left:
                st.subheader("Solution")
                st.json(solution)
            with right:
                st.subheader("Independent Validation")
                st.json(report.to_dict())
            if comparison.alternative is not None and comparison.alternative_report is not None:
                st.subheader("Alternative solution and independent validation")
                st.json(comparison.alternative)
                st.json(comparison.alternative_report.to_dict())

        if comparison.alternative is None:
            st.download_button(
                "Download Slide 8 Official Submission JSON",
                data=json.dumps(format_official_submission(plan, solution, report), indent=2),
                file_name=f"official_submission_{plan_id}.json",
                mime="application/json",
            )
    except Exception as error:
        st.error(f"Run failed: {error}")
