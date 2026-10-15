"""Complete end-to-end integration demo connecting Harshit, Priyanshu, and Sana.

Pipeline:
  1. Raw input / Normalized Plan (Harshit)
  2. Capacity-constrained ring optimizer (Priyanshu)
  3. Independent hard-rule validation & recomputed metrics (Sana)
  4. Verified visual overlay and exported combined JSON (Sana)
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple

from shapely.geometry import box

# Ensure workspace packages can be imported
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "harshit") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "harshit"))
if str(REPO_ROOT / "priyanshu") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "priyanshu"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sana.validation.checker import IndependentValidator
from sana.validation.models import ValidationReport
from sana.visualization.renderer import render_solution_overlay


def run_full_pipeline(
    raw_dict: Optional[Dict[str, Any]] = None,
    plan_dict: Optional[Dict[str, Any]] = None,
    render_path: Optional[str] = "end_to_end_overlay.png",
    export_json_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], ValidationReport]:
    """
    Execute full pipeline from raw/plan to solved, validated, and rendered output.
    """
    # Step 1: Normalization (Harshit) if raw input is provided
    if raw_dict is not None:
        try:
            from ingestion.normalize import normalize_plan
            norm_res = normalize_plan(raw_dict)
            if not norm_res.ok:
                raise ValueError(f"Plan normalization failed: {norm_res.diagnostics}")
            plan = norm_res.plan
        except ImportError as e:
            raise ImportError(f"Could not import Harshit's normalizer: {e}")
    elif plan_dict is not None:
        plan = plan_dict
    else:
        raise ValueError("Must provide either raw_dict or plan_dict")

    # Step 2: Optimization (Priyanshu)
    try:
        from solver.thin_slice import solve
        solution = solve(plan)
    except ImportError as e:
        raise ImportError(f"Could not import Priyanshu's solver: {e}")

    # Step 3: Independent Hard-Rule Validation & Metric Recomputation (Sana)
    validator = IndependentValidator()
    report = validator.validate(plan, solution)

    # Step 4: Visual Overlay (Sana)
    if render_path:
        Path(render_path).parent.mkdir(parents=True, exist_ok=True)
        render_solution_overlay(plan, solution, report, output_path=render_path)

    # Optional: Export verified combined interchange JSON
    if export_json_path:
        combined = {
            "schema_version": "0.1.0",
            "plan": plan,
            "solution": {
                **solution,
                # Replace optimizer metrics with independent checked metrics
                "metrics": report.recomputed_metrics.to_dict() if report.recomputed_metrics else solution.get("metrics"),
            },
        }
        with open(export_json_path, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)

    return plan, solution, report


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-End Pipeline Demo (Harshit + Priyanshu + Sana)")
    parser.add_argument("--plan", type=str, help="Path to normalized Plan JSON (e.g. priyanshu/tests/fixtures/three_room_plan.json)")
    parser.add_argument("--sample-raw", action="store_true", help="Run with a synthetic 2-room ResPlan raw geometry item")
    parser.add_argument("--render", type=str, default="end_to_end_result.png", help="Path to save overlay image")
    parser.add_argument("--export", type=str, help="Path to export verified combined JSON")

    args = parser.parse_args()

    if args.sample_raw:
        # Synthetic raw item matching Harshit's ResPlan format
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
        print("Running end-to-end with synthetic ResPlan raw geometry...")
        plan, solution, report = run_full_pipeline(raw_dict=raw_input, render_path=args.render, export_json_path=args.export)
    elif args.plan:
        with open(args.plan, "r", encoding="utf-8") as f:
            plan_input = json.load(f)
        print(f"Running end-to-end with normalized plan: {args.plan}...")
        plan, solution, report = run_full_pipeline(plan_dict=plan_input, render_path=args.render, export_json_path=args.export)
    else:
        # Default to Priyanshu's three_room_plan fixture
        default_fixture = REPO_ROOT / "priyanshu" / "tests" / "fixtures" / "three_room_plan.json"
        if default_fixture.exists():
            with open(default_fixture, "r", encoding="utf-8") as f:
                plan_input = json.load(f)
            print(f"Running end-to-end with default fixture: {default_fixture}...")
            plan, solution, report = run_full_pipeline(plan_dict=plan_input, render_path=args.render, export_json_path=args.export)
        else:
            parser.print_help()
            return 2

    print("\n" + "=" * 60)
    print("PIPELINE EXECUTION COMPLETE")
    print("=" * 60)
    print(report.summary())
    if args.render:
        print(f"\nVerified Overlay saved to: {args.render}")
    if args.export:
        print(f"Verified Combined JSON exported to: {args.export}")

    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
