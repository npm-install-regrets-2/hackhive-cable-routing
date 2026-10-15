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
3. Put small hand-checked examples in `shared/fixtures/` when at least two workspaces use them. Preserve IDs and drawing-unit coordinates in the development contract. Record expected feasibility and metric arithmetic beside the fixture.
4. Harshit owns the meaning and construction of portals and geometric legality queries. Priyanshu uses those results to construct routes. Sana checks the final submitted geometry independently against the same challenge rules.
5. A shared interface change needs the producing developer and affected consumers to review it before merging.
6. The slide-8 team submission is a separate export in metres, not the drawing-unit `Solution` or complete development wrapper. Priyanshu supplies solved geometry; Sana owns the checked export/overlay integration. Review an export adapter against the full organizer schema if one becomes available.

## Parallel workflow

Each developer clones the same repository, creates a branch for a small task, updates their progress log, and opens a pull request. Another developer reviews the PR; the project owner merges it into `main`. After a merge, developers update their branches from `main` before building on the changed contract. Merge the first fixture and vertical slice early, then continue with smaller PRs instead of waiting for all three workspaces to be finished.

## Current assumptions to keep configurable

The reviewed eight-slide `Cable Ring Challenge - Problem Statement4.pptx` confirms fixed input nodes, a hub inside one of its assigned eligible rooms and at least 0.5 m from walls, five nodes per hub, and an abridged metre-coordinate team-output example. The deck does not give a machine-readable fixed-node input schema or complete submission schema, and excluded-interior-room transit still needs clarification. Use the development assumptions in `PROJECT_PLAN.md`, label fallback node data clearly, and keep capacities/tolerances configurable. Do not submit the drawing-unit development JSON as the slide-8 output without conversion and validation.
