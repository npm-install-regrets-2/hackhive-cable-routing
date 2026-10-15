# Collaboration Guide

This repository has three temporary developer workspaces. Keep implementation code inside the assigned workspace until the first integration pass; the folders may be renamed when the branches are merged.

## Source of truth

- Read `PROJECT_PLAN.md` before changing behavior or constraints.
- Read `CONTEXT.md` before naming domain objects. Use `hub`, `node`, `territory`, `portal`, `ring`, and `leg` as defined there.
- Read `shared/schema/common.schema.json` before producing or consuming plan or solution JSON. It is the development interchange contract; an organizer-provided schema supersedes it.
- Read `docs/README.md` before implementation. Update your progress log after each meaningful implementation step so teammates can resume from it.
- Read `docs/workstreams.md` before starting or reviewing a task that crosses workspaces.
- Treat capacities and tolerances as configuration. The current defaults are 100 m² and five nodes per hub.

## Ownership

### `harshit/`

Own input loading, ResPlan normalization, unit conversion, eligible-room extraction, fixed-node loading/fallback generation, obstacle and portal geometry, traversability construction, and geometric primitives needed by the other workspaces.

Completion criterion: a normalized `Plan` conforming to the shared schema can be produced from a dataset item, with stable room/node/portal IDs and explicit diagnostics for unusable geometry.

### `priyanshu/`

Own legal hub-candidate generation using Harshit's geometry contract, minimum-hub connected assignment, rectilinear pathfinding, per-hub closed-ring ordering, fixed-hub-count improvement, and solution serialization.

Completion criterion: a schema-valid normalized `Plan` can be consumed to produce a schema-valid `Solution`, with infeasibility or best-known status reported explicitly. Sana's validator independently checks feasibility and metrics.

### `sana/`

Own independent validation of every hard rule, metric recomputation and ranking, solution diagnostics, visual overlays, and the end-to-end demo that connects the normalized input, solver output, and checked result.

Completion criterion: a `Plan` and `Solution` can be checked without importing Priyanshu's optimizer, and the displayed overlay and metrics are derived from the checked solution.

### `shared/`

Contains only stable interfaces and fixtures needed across workspaces. Changes here require impact review by the producer and every affected consumer. Keep algorithms and developer-specific utilities out of this folder.

## Integration rules

1. Exchange data only through objects represented by `shared/schema/common.schema.json`.
2. Preserve IDs from input to output; geometry joins use IDs, never array positions.
3. Coordinates remain in drawing units. Length and area fields whose names end in `_m` or `_m2` are physical measurements.
4. A polygon ring is closed: its last point equals its first point. A cable ring is also closed and begins and ends at its owning hub.
5. Emit deterministic output for identical input and configuration, including stable array ordering.
6. Validate at each boundary. Reject malformed or infeasible data with structured diagnostics instead of silently repairing it.
7. Add tests and fixtures in the workspace that owns the behavior. Shared fixtures belong in `shared/fixtures/` when multiple workspaces consume them.
8. Cross-workspace interaction goes through the shared contract. During integration, promote stable code into final package names and update imports in one dedicated merge change.
9. Develop on task branches. Another developer reviews each pull request; the project owner merges it into `main`.

## Shared-schema changes

Before editing the schema, state the producer, consumers, compatibility effect, and migration. Prefer additive optional fields during parallel development. If a breaking change is necessary, update `schema_version`, all affected workspace adapters, and the shared fixtures together.

## Definition of done

A change is complete when its owned tests pass, emitted JSON validates against the shared schema, terminology matches `CONTEXT.md`, any assumption not confirmed by the challenge material is configurable and documented, and its progress log is current.
