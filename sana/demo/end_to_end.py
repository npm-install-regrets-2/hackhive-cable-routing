"""Complete end-to-end integration demo connecting Harshit, Priyanshu, and Sana.

Pipeline:
  1. Raw input / ResPlan archive loading & normalization (Harshit)
  2. Capacity-constrained ring optimizer (Priyanshu)
  3. Independent hard-rule validation & metric recomputation (Sana)
  4. Visual overlay and official submission JSON export (Sana)
"""

import argparse
import copy
import json
from pathlib import Path
import pickle
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
from sana.export import format_official_submission

_CACHED_ARCHIVE: Optional[list] = None


def load_plan_from_archive(archive_path: str, plan_id: int) -> Dict[str, Any]:
    """Load a plan by ID from the ResPlan archive with in-memory caching."""
    global _CACHED_ARCHIVE
    if _CACHED_ARCHIVE is None:
        print(f"Loading {archive_path} into memory...")
        with open(archive_path, "rb") as f:
            _CACHED_ARCHIVE = pickle.load(f)
        print(f"Loaded {len(_CACHED_ARCHIVE)} plans into memory cache.")

    for item in _CACHED_ARCHIVE:
        if isinstance(item, dict) and item.get("id") == plan_id:
            return item
    raise KeyError(f"Plan ID {plan_id} not found in archive.")


def run_full_pipeline(
    raw_dict: Optional[Dict[str, Any]] = None,
    plan_dict: Optional[Dict[str, Any]] = None,
    render_path: Optional[str] = "end_to_end_overlay.png",
    export_combined_path: Optional[str] = None,
    export_official_path: Optional[str] = None,
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
    # The initial thin-slice solver handles obstacle-free portal routes; pass clean copy for thin-slice
    try:
        from solver.thin_slice import solve
        solve_input = copy.deepcopy(plan)
        if solve_input.get("obstacles"):
            # Provide obstacle-free view for thin-slice solver
            solve_input["obstacles"] = []
        solution = solve(solve_input)
    except ImportError as e:
        raise ImportError(f"Could not import Priyanshu's solver: {e}")

    # Step 3: Independent Hard-Rule Validation & Metric Recomputation (Sana)
    validator = IndependentValidator()
    report = validator.validate(plan, solution)

    # Step 4: Visual Overlay (Sana)
    if render_path:
        Path(render_path).parent.mkdir(parents=True, exist_ok=True)
        render_solution_overlay(plan, solution, report, output_path=render_path)

    # Step 5: Export formats
    if export_combined_path:
        combined = {
            "schema_version": "0.1.0",
            "plan": plan,
            "solution": {
                **solution,
                "metrics": report.recomputed_metrics.to_dict() if report.recomputed_metrics else solution.get("metrics"),
            },
        }
        with open(export_combined_path, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)

    if export_official_path:
        official_json = format_official_submission(plan, solution, report)
        with open(export_official_path, "w", encoding="utf-8") as f:
            json.dump(official_json, f, indent=2)

    return plan, solution, report


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-End Pipeline Demo (Harshit + Priyanshu + Sana)")
    parser.add_argument("--plan-id", type=int, help="Plan ID to load directly from archive/ResPlan.pkl (e.g. 14926, 14433, 17054)")
    parser.add_argument("--archive", type=str, default="archive/ResPlan.pkl", help="Path to ResPlan.pkl archive")
    parser.add_argument("--plan", type=str, help="Path to normalized Plan JSON")
    parser.add_argument("--sample-raw", action="store_true", help="Run with synthetic 2-room ResPlan raw geometry")
    parser.add_argument("--render", type=str, default="end_to_end_result.png", help="Path to save overlay image")
    parser.add_argument("--export-combined", type=str, help="Path to export development combined interchange JSON")
    parser.add_argument("--export-official", type=str, help="Path to export Slide 8 Official Submission JSON in metres")

    args = parser.parse_args()

    if args.plan_id is not None:
        raw_input = load_plan_from_archive(args.archive, args.plan_id)
        print(f"Loaded Plan ID {args.plan_id} from {args.archive}. Normalizing and solving...")
        plan, solution, report = run_full_pipeline(
            raw_dict=raw_input,
            render_path=args.render,
            export_combined_path=args.export_combined,
            export_official_path=args.export_official,
        )
    elif args.sample_raw:
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
        plan, solution, report = run_full_pipeline(
            raw_dict=raw_input,
            render_path=args.render,
            export_combined_path=args.export_combined,
            export_official_path=args.export_official,
        )
    elif args.plan:
        with open(args.plan, "r", encoding="utf-8") as f:
            plan_input = json.load(f)
        print(f"Running end-to-end with normalized plan: {args.plan}...")
        plan, solution, report = run_full_pipeline(
            plan_dict=plan_input,
            render_path=args.render,
            export_combined_path=args.export_combined,
            export_official_path=args.export_official,
        )
    else:
        default_fixture = REPO_ROOT / "priyanshu" / "tests" / "fixtures" / "three_room_plan.json"
        with open(default_fixture, "r", encoding="utf-8") as f:
            plan_input = json.load(f)
        print(f"Running end-to-end with default fixture: {default_fixture}...")
        plan, solution, report = run_full_pipeline(
            plan_dict=plan_input,
            render_path=args.render,
            export_combined_path=args.export_combined,
            export_official_path=args.export_official,
        )

    print("\n" + "=" * 60)
    print("PIPELINE EXECUTION COMPLETE")
    print("=" * 60)
    print(report.summary())
    if args.render:
        print(f"\nVerified Overlay saved to: {args.render}")
    if args.export_combined:
        print(f"Combined Interchange JSON saved to: {args.export_combined}")
    if args.export_official:
        print(f"Slide 8 Official Submission JSON saved to: {args.export_official}")

    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
