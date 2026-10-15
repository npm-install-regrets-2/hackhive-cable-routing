# Priyanshu's progress

Append entries using the format in `docs/README.md`. Owns hub assignment, pathfinding, closed rings, and optimization.

## 2026-10-15 — Schema-valid thin solver slice

- Status: done
- Changed: `priyanshu/solver/`, `priyanshu/tests/fixtures/three_room_plan.json`, `priyanshu/tests/test_thin_slice.py`, `priyanshu/pyproject.toml`, and `priyanshu/README.md`
- Why: establish a deterministic, proof-oriented vertical slice while Harshit's normalized loader and geometry kernel are in progress
- Checked: `uv run pytest` from `priyanshu/`; 5 tests passed, including Plan/Solution/complete-export validation against `shared/schema/common.schema.json`
- Open: obstacle-aware free-space geometry and authoritative legal hub-candidate generation still require Harshit's geometry capability; fixture-scale exhaustive search is not intended for production plan sizes
- Next: replace room-center candidates and sampled rectangular routing with Harshit's legal candidate/free-space queries, then introduce scalable connected assignment and path caching
- Commit/PR: `8083b4f`; https://github.com/npm-install-regrets-2/hackhive-cable-routing/pull/1

## 2026-10-15 — Eight-slide deck and notes alignment

- Status: done (documentation audit; implementation gaps remain)
- Changed: `PROJECT_PLAN.md`, `docs/workstreams.md`, `priyanshu/README.md`, and this log; no schema or algorithm changes
- Why: the complete deck confirms a hub must be in an assigned eligible room at least 0.5 m from walls, clarifies same-line overlap versus parallel retrace, and shows a metre-coordinate submission format distinct from the drawing-unit development contract
- Checked: read all eight slides and their speaker notes; compared scale, hub bound, `J`, and metric definitions with the current normalizer, thin solver, checker, and schema; reviewed the documentation diff and whitespace checks
- Open: thin-slice crossings/overlap are zero placeholders and bends omit node/hub joins; independent checker still needs hub clearance, hub-room assignment, and portal-only boundary checks; fixed-node input and complete output schemas remain unavailable
- Next: implement focused rule/metric regression tests and legal hub candidates with Harshit's geometry contract; coordinate checker and submission adapter changes with Sana before changing the shared schema
- Commit/PR: pending documentation branch review

## 2026-10-16 — Score and reroute tours to eliminate plan 13033 crossings

- Status: done
- Changed: `priyanshu/solver/grid_router.py`, `priyanshu/tests/test_grid_router.py`, `kaggle_13033_combined.json`, `official_submission_13033.json`
- Why: the grid router previously selected a ring by length and bends, then reported the checker's crossing penalty only afterward; building all legs in stop order also missed legal crossing-free paths
- Checked: `python -m pytest priyanshu/tests sana/tests/test_hub_placement_scenarios.py -q` (13 passed); independently validated regenerated plan 13033 output and schema (3 hubs, living → bedroom 000 → bedroom 001, 0 crossings, 0 overlap, cost 45.2309 versus 60.2309 originally)
- Open: global cost optimality is not established; partition and hub candidate selection still use first feasible choices, and cross-ring interactions are scored only after routing
- Next: compare full solution cost across connected partitions and hub candidates
- Commit/PR: pending

## 2026-10-16 — Remove plan 14433 bedroom 002 crossing

- Status: done
- Changed: `priyanshu/solver/grid_router.py`, `priyanshu/tests/test_grid_router.py`, `kaggle_14433_combined.json`, `official_submission_14433.json`
- Why: the remaining crossing came from routing bedroom 002's entry and exit through the doorway in the wrong lane order; the alternate leg-construction pass now also runs for four-node territories
- Checked: `python -m pytest priyanshu/tests sana/tests/test_hub_placement_scenarios.py -q` (14 passed); independent validator and shared schema accept regenerated plan 14433 output (2 hubs, 0 crossings, 0 overlap, cost 52.8248 versus 57.9508 previously)
- Open: global cost optimality and cross-ring interaction optimization remain unproven
- Next: compare full solution cost across hub candidates and connected partitions
- Commit/PR: pending

## 2026-10-16 — Compare connected territory partitions by complete route cost

- Status: done
- Changed: `priyanshu/solver/grid_router.py`, `priyanshu/tests/test_grid_router.py`, both Kaggle combined outputs and their official submissions
- Why: the solver returned the first feasible connected partition, leaving lower-cost valid territory assignments unexamined; the two saved plans also showed uneven node counts that needed a graph/capacity check
- Checked: `python -m pytest priyanshu/tests sana/tests/test_hub_placement_scenarios.py -q` (16 passed); independent validator and shared schema accept regenerated outputs: plan 13033 costs 32.8762 with 0 crossings and plan 14433 costs 49.4166 with 0 crossings; the portal graph forces 3–1–1 and 4–1 node splits respectively
- Open: the partition list is capped at 50, hub placement still chooses one candidate per territory, and per-territory route search remains heuristic; full cost optimality is not proven
- Next: broaden hub-candidate and route search under a measured runtime budget, preserving independently checked best results
- Commit/PR: pending

## 2026-10-16 — Joint hub candidate exploration across connected territories

- Status: done
- Changed: `priyanshu/solver/grid_router.py`, `priyanshu/tests/test_grid_router.py`, `kaggle_13033_combined.json`, `kaggle_14433_combined.json`, `official_submission_13033.json`, `official_submission_14433.json`
- Why: the solver previously picked only a single greedy hub candidate per territory (by degree and area), bypassing lower-cost hub placements within valid territories
- Checked: `pytest priyanshu/tests sana/tests/ -v` (30 passed); verified with `IndependentValidator` and schema validation; plan 13033 route cost J improved from 32.8762 to 31.6972 (length reduced to 24.6972 m, 0 crossings, 0 overlap), plan 14433 route cost J improved from 49.4166 to 46.6841 (bends reduced from 24 to 20, length reduced to 36.6841 m, 0 crossings, 0 overlap)
- Open: partition search remains capped at 50 partitions and candidate search capped at 3 per territory to maintain runtime predictability
- Next: evaluate multi-ring cable lane spacing or further rectilinear Steiner / Hanan pruning if runtime budget allows
- Commit/PR: pending
