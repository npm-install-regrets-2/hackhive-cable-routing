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

## Thin solver slice

The first fixture-scale implementation lives in `solver/thin_slice.py`. It:

- computes the simultaneous area/node hub-count lower bound;
- exhaustively searches deterministic room-center candidates and connected,
  capacity-compliant territories, proving optimality only when a solution meets
  the arithmetic lower bound;
- orders each territory's nodes by exhaustive tour search and builds closed,
  axis-aligned legs through verified portals; and
- returns a schema-shaped explicit infeasibility result when the supported
  geometry cannot be solved.

This implementation intentionally accepts only obstacle-free normalized plans.
It is a proof-oriented integration slice, not the production-scale optimizer or
Harshit's future geometry kernel. From this directory, run it with `uv run pytest`.
