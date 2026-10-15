"""End-to-end demo and verification runner connecting plan, solution, validation, and rendering."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sana.validation.checker import IndependentValidator
from sana.validation.models import ValidationReport
from sana.visualization.renderer import render_solution_overlay


def load_input_files(
    plan_path: Optional[str] = None,
    solution_path: Optional[str] = None,
    combined_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Load plan and solution from separate files or a single combined interchange JSON."""
    if combined_path:
        with open(combined_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["plan"], data["solution"]

    if not plan_path or not solution_path:
        raise ValueError("Must specify either --combined or both --plan and --solution")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    with open(solution_path, "r", encoding="utf-8") as f:
        solution = json.load(f)

    return plan, solution


def run_pipeline(
    plan: Dict[str, Any],
    solution: Dict[str, Any],
    render_output_path: Optional[str] = None,
) -> ValidationReport:
    """Run independent validator, recompute metrics, and optionally render visual overlay."""
    validator = IndependentValidator()
    report = validator.validate(plan, solution)

    if render_output_path:
        Path(render_output_path).parent.mkdir(parents=True, exist_ok=True)
        render_solution_overlay(plan, solution, report, output_path=render_output_path)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Sana workspace validator and visualizer runner")
    parser.add_argument("--plan", type=str, help="Path to normalized Plan JSON")
    parser.add_argument("--solution", type=str, help="Path to Solution JSON")
    parser.add_argument("--combined", type=str, help="Path to combined interchange JSON")
    parser.add_argument("--render", type=str, default="verified_overlay.png", help="Path to save overlay image")
    parser.add_argument("--json", action="store_true", help="Print report as JSON")

    args = parser.parse_args()

    try:
        plan, solution = load_input_files(args.plan, args.solution, args.combined)
    except Exception as e:
        print(f"Error loading inputs: {e}", file=sys.stderr)
        return 2

    report = run_pipeline(plan, solution, render_output_path=args.render)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary())
        if args.render:
            print(f"\nOverlay saved to: {args.render}")

    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
