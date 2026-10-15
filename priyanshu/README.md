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

## Deck-alignment work remaining

The reviewed eight-slide challenge deck makes hub placement stricter than the
thin slice currently proves: each hub must be inside an eligible room assigned
to it and at least 0.5 m from walls. Candidate generation and the independent
checker must enforce this before a result can be called challenge-valid. The
thin slice's `metrics` are advisory: it currently reports zero crossings and
overlap and misses bends at leg joins, nodes, and hubs. Use Sana's independently
recomputed metrics for review, and do not claim an optimal `J` from this slice.

The shared `Solution` uses drawing-unit points. Slide 8's abridged team-output
example requires metre-coordinate locations and polylines, so it needs a
separate, checked export adapter; a schema-valid development `Solution` is not
itself a submission file. Keep fixed organizer nodes immutable; development
fallback nodes must remain clearly labelled.
