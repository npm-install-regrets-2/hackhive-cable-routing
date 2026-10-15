# Sana workspace

Ownership: independent validation, scoring, visualization, and the end-to-end demo.

Start with these modules when implementation begins:

- `validation/`: schema checks and independent hard-rule checks for assignments, capacities, connectivity, ring visits, closure, and cable legality
- `metrics/`: recompute hub count, cable length, crossings, overlap, bends, route cost, and area-gap tie-break from submitted geometry
- `visualization/`: draw the normalized plan, assignments, hubs, nodes, cable rings, and diagnostics from the checked result
- `demo/`: connect normalized input, optimizer output, validation, and the visual/JSON export
- `tests/`: hand-checked fixtures and tests for owned behavior

Consume `Plan` and `Solution` through `../shared/schema/common.schema.json`. Keep validation and metric calculations independent of Priyanshu's optimizer. Use shared fixtures while the other workspaces are in progress, and log each meaningful step in `../docs/progress/sana.md`.
