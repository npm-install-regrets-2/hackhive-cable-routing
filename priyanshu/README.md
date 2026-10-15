# Priyanshu workspace

Ownership: optimization and route construction.

Start with these modules when implementation begins:

- `candidates/`: finite legal hub-candidate generation
- `assignment/`: minimum-hub, capacity-compliant, connected territories
- `pathfinding/`: legal axis-aligned hub-node and node-node paths
- `routing/`: one closed ring per hub and exactly-once node ordering
- `improvement/`: fixed-hub-count optimization of route cost and area gap
- `tests/`: fixtures and tests for all owned behavior

Consume normalized `Plan` data and emit `Solution` data through `../shared/schema/common.schema.json`. Use shared fixtures while Harshit's loader is in progress. Sana independently checks the result; keep claimed metrics advisory. Log each meaningful step in `../docs/progress/priyanshu.md`.
