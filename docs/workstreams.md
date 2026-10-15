# Three-developer work split

This is the agreed temporary ownership while the team develops in parallel. `PROJECT_PLAN.md` defines the problem and phases; `AGENTS.md` defines the repository rules. The temporary developer folders can be consolidated after an end-to-end run works.

| Developer | Owns | Produces | Starts with |
| --- | --- | --- | --- |
| Harshit | ResPlan loading, unit conversion, eligible-room and fixed-node input, polygon components, obstacles, portals, traversability | Normalized `Plan` with stable IDs and geometry diagnostics | One dataset item converted into the shared plan shape; a small synthetic plan fixture |
| Priyanshu | Hub candidates, connected capacity-constrained assignment, legal axis-aligned paths, closed ring order, route improvement | `Solution` with hubs, exclusive assignments, rings, and status | A small schema-valid plan fixture; minimum-hub assignment and one legal ring |
| Sana | Independent hard-rule validator, checker-style metrics and ranking, visual overlay, end-to-end demo | Validation report, recomputed score, matching visual/JSON view | Hand-checked plan/solution fixtures with valid and invalid cases |

## Handoffs

1. The shared schema is the data boundary. Harshit produces `plan`; Priyanshu consumes `plan` and produces `solution`; Sana consumes both. The complete export wraps both in `schema_version`, `plan`, and `solution`.
2. During parallel development, each team can validate its own object against `#/$defs/plan` or `#/$defs/solution` in `shared/schema/common.schema.json`. The root schema validates the combined export.
3. Put small hand-checked examples in `shared/fixtures/` when at least two workspaces use them. Preserve IDs and drawing-unit coordinates. Record expected feasibility and metric arithmetic beside the fixture.
4. Harshit owns the meaning and construction of portals and geometric legality queries. Priyanshu uses those results to construct routes. Sana checks the final submitted geometry independently against the same challenge rules.
5. A shared interface change needs the producing developer and affected consumers to review it before merging.

## Parallel workflow

Each developer clones the same repository, creates a branch for a small task, updates their progress log, and opens a pull request. Another developer reviews the PR; the project owner merges it into `main`. After a merge, developers update their branches from `main` before building on the changed contract. Merge the first fixture and vertical slice early, then continue with smaller PRs instead of waiting for all three workspaces to be finished.

## Current assumptions to keep configurable

The team has no newer organizer material for fixed node coordinates, hub placement legality, or the final output JSON format. Use the development assumptions in `PROJECT_PLAN.md`, label fallback node data clearly, and adapt the output if the official schema arrives. The newer slides specify five nodes per hub; the older statement says twenty, so keep this limit configurable as the plan requires.
