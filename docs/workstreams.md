# Module responsibilities

The initial parallel workspaces were consolidated into `cable_planner/`. Historical work is recorded in `docs/progress/harshit.md`, `docs/progress/priyanshu.md`, and `docs/progress/sana.md`.

| Module | Responsibility | Interface |
| --- | --- | --- |
| `ingestion/`, `geometry/` | Normalize trusted ResPlan input, preserve stable IDs, derive rooms, nodes, obstacles, and verified portals | Schema-valid `Plan` and structured diagnostics |
| `solver/` | Generate legal hub candidates, assign connected territories, route axis-aligned closed rings, and report feasibility | `cable_planner.solver.solve(plan)` returning `Solution` |
| `validation/`, `metrics/` | Independently check hard rules and recompute H, L, X, O, B, J, and area gap | `IndependentValidator.validate(plan, solution)` |
| `visualization/`, `demo/`, `export.py` | Show checked input/output overlays and produce development or official-format JSON | Checked report and files |

The shared schema is the seam between the normalized Plan and Solution. A schema change requires review by the producer and each affected consumer. The optimizer and validator must remain independently implemented so the validator can detect solver defects.

The challenge materials have not confirmed fixed node coordinates, exact hub-placement legality, or the final organizer schema. The development fallback nodes and the configurable capacity/tolerance assumptions remain documented in `PROJECT_PLAN.md`.
