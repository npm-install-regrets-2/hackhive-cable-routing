# Repository Guide

## Read before changing behavior

- `PROJECT_PLAN.md`: challenge rules, objective order, and configurable assumptions.
- `CONTEXT.md`: domain terms for hubs, nodes, territories, portals, rings, and legs.
- `shared/schema/common.schema.json`: development interchange contract for Plan and Solution JSON.
- `docs/workstreams.md`: module responsibilities and integration history when a change spans modules.
- `docs/README.md`: progress-log format.

## Package layout

- `cable_planner/ingestion/` and `cable_planner/geometry/` normalize trusted input and derive verified traversability.
- `cable_planner/solver/` selects hubs, assigns connected territories, and constructs closed cable rings. `cable_planner.solver.solve` is the current obstacle-aware solver.
- `cable_planner/validation/` and `cable_planner/metrics/` check solutions independently of the solver and recompute their score.
- `cable_planner/visualization/`, `cable_planner/demo/`, and `cable_planner/export.py` present and export checked results.
- `shared/` contains stable schema and cross-module fixtures; `tests/` holds focused tests by responsibility.

## Integration rules

1. Exchange Plan and Solution data through `shared/schema/common.schema.json`; preserve input IDs in output. Join geometry by ID, not array position.
2. Keep coordinates in drawing units. Fields ending in `_m` or `_m2` contain physical measurements.
3. Polygon rings are closed. Each cable ring starts and ends at its owning hub.
4. Emit deterministic output for identical input and configuration. Report malformed or infeasible data with structured diagnostics.
5. Keep the 100 m² area limit, five-node limit, and geometry tolerances configurable. Follow the objective order in `PROJECT_PLAN.md`.
6. Validate at module seams. Solver claims are advisory; independent validation and recomputed metrics determine the displayed result.
7. Put tests in the corresponding `tests/` area. Add shared fixtures only when multiple modules consume them.
8. For schema changes, record the producer, consumers, compatibility effect, and migration before editing. Prefer additive optional fields; update the schema version, adapters, and fixtures together for a breaking change.
9. Develop on task branches, update `docs/progress/integration.md` after meaningful integration work, and have another developer review a pull request before the project owner merges it into `main`.

A change is complete when its relevant tests pass, emitted JSON validates against the shared schema, terminology matches `CONTEXT.md`, and any unconfirmed challenge assumption remains configurable and documented.
