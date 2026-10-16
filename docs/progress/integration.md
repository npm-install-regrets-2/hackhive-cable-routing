# Integration progress

## 2026-10-16 — Add configurable cable-to-wall clearance

- Status: done
- Changed: `cable_planner/solver/grid_router.py`; the solver accepts `cable_wall_clearance_m` (default 0.03 m), buffers wall obstacles by that amount, and adds offset Hanan-grid lanes. Fixed hub/node coordinates are unchanged.
- Why: saved plan 13033 and 14433 routes included segments within approximately 0.1 mm of wall geometry; wall-edge contact was being accepted and the grid offered no small-offset alternative.
- Checked: plan 14433 solved and passed independent validation with 0 violations. At 0 clearance it took 61.537 s with J=46.6841; at 0.03 m it took 67.066 s with J=47.1666, and minimum measured wall gap was 0.0628 m. The clearance change added about 5.5 s (~9%) on this run.
- Open: representative-plan runtime is dominated by the existing partition, hub-candidate, and ring-order search; verify door clearances before relying on the 0.03 m default for narrow openings.
- Next: tune route separation through shared open passages and keep the cost/runtime tradeoff visible.
- Commit/PR: pending

## 2026-10-16 — Improve floor overlay clarity

- Status: done
- Changed: `cable_planner/visualization/renderer.py`
- Why: distinguish room kinds and architectural features in the output diagram, keep labels legible over routes, and make co-located hub/node symbols readable
- Checked: `.venv\\Scripts\\python.exe -m pytest` (42 passed); the 13033 and 14433 routing-cost assertions passed with the existing solver
- Open: rendered cable geometry is unchanged; it can still be close to a wall in the underlying coordinates
- Next: review a representative generated overlay
- Commit/PR: `c6591d7` on `fix/floor-diagram-clarity`; push pending destination approval

## 2026-10-16 — Stop depicting open passages as doors

- Status: done
- Changed: `cable_planner/visualization/renderer.py`; only actual doors receive a portal stroke. Open passages remain visually open.
- Why: the thick marker over a shared open boundary looked like an imaginary door, even though the solver routed through the open passage.
- Checked: inspected plan 14433's normalized portal and wall geometry; its living–kitchen open passage is about 58.9 drawing units long, and cable legs 2 and 3 cross it at y=158.5 and y=160.41. Removed both the open-passage marker and the duplicated room-outline stroke from the opening in input and solution views.
- Open: cable paths still cross the same opening only 1.91 drawing units apart; increasing their separation may affect route cost and runtime.
- Next: review the updated overlay and choose a cable separation target if needed.
- Commit/PR: pending

## 2026-10-16 — Keep close hub and node symbols readable

- Status: done
- Changed: `cable_planner/visualization/renderer.py`; when a hub is within 0.5 m of a fixed node, its rectangular badge moves aside with a leader and the actual hub point stays marked. Short room labels avoid hubs, nodes, and routes, and cable strokes render above labels.
- Why: plan 14433's H2 and N3 are only 1.23 drawing units apart; the large hub badge covered the short loop and node marker.
- Checked: rendered plan 14433's saved solution and independently validated it (0 violations, J=46.6841); the H2 label no longer covers N3 and the loop is visible. Rendering changes do not modify solver coordinates or cost. The current 0.03 m solve also validates with 0 violations, J=47.1666, in 66.022 s.
- Open: cable paths still cross the same open passage only 1.91 drawing units apart; increasing their separation may affect route cost and runtime.
- Next: compare the current 0.03 m route's H2 ring against the updated saved-solution preview if a new full solver output is needed.
- Commit/PR: pending

## 2026-10-16 — Speed up interaction-aware routing and clarify retraces

- Status: done
- Changed: `cable_planner/solver/grid_router.py`, `cable_planner/visualization/renderer.py`, `tests/solver/test_grid_router.py`, `tests/validation/test_visualization.py`
- Why: plan 14433 routing repeatedly scanned every Hanan-grid edge after each leg; the overlay also needed to distinguish true shared-line retraces from close parallel return legs.
- Changed: index graph edges by horizontal row and vertical column when applying existing route-interaction penalties, and remove the redundant graph reachability traversal before A*. Draw a two-headed arrow only over a geometric span shared by multiple cable legs. Preserve the hub's actual solver point and cost.
- Checked: focused penalty-equivalence and retrace-vs-parallel checks passed (2 passed). Plan 14433 at the existing 0.03 m wall clearance solved in 38.632 s (previous recorded run: 66.022 s), independently validated with zero violations, and kept the same J=47.166637, L=37.166637 m, X=0, O=0, B=20, and area gap=77.4652 m². Updated overlay saved as `tmp/plan14433-cable-fix.png`. The living–kitchen opening remains a verified 58.909-unit open passage; the two routes cross its boundary line at y=158.50 and 160.41 inside the opening range y=129.04–187.95. No wall obstacle intersects the opening.
- Check limitation: three selected checks passed, but the visualization test that allocates `tmp_path` could not set up/clean its pytest temporary directory under the sandbox; rendering itself was verified by the saved overlay and independent validation.
- Open: the two cables still pass 1.91 drawing units apart through the wide passage; this is separate parallel routing, not wall clearance or overlap.
- Next: review the updated diagram and determine whether additional visual separation in the open passage is desired.
- Commit/PR: pending

## 2026-10-16 — Apply additional runtime speedups

- Status: done
- Changed: `cable_planner/solver/grid_router.py`; merged the provided `runtime-speedup.patch` with the existing worktree changes.
- Changed: A* now stores parent pointers instead of copying full paths into each priority-queue entry, reads graph adjacency directly, and relies on A* itself to report unreachable targets. Visit permutations are considered in Manhattan lower-bound order and pruned once they cannot beat the best complete ring. Edge interaction penalties use a cached row/column edge index with interval lookups.
- Checked: four focused solver/renderer checks passed. Plan 14433 solved in 17.462 s with independent validation (zero violations): H=2, J=47.166637, L=37.166637 m, X=0, O=0, B=20, area gap=77.4652 m². This preserves the prior 38.632 s run's metrics and is about 73.5% faster than the recorded 66.022 s run. The updated image and solution JSON are in `tmp/`.
- Open: none introduced by the optimization; the living–kitchen open passage is unchanged and no wall obstacle crosses it.
- Next: review the updated overlay and merge when ready.
- Commit/PR: pending

## 2026-10-16 — Verify runtime patch against a clean base

- Status: done
- Changed: `cable_planner/solver/grid_router.py`; the supplied patch applies cleanly to a copy of `HEAD`. Its A*, Manhattan-order pruning, and cached edge index are integrated into the active solver, while the existing 0.03 m wall-clearance setting is preserved.
- Checked: in this environment, the patch applied to clean `HEAD` measured 17.704 s on plan 14433 and 5.899 s on plan 13033 (no wall-clearance feature in that base). The active solver measured 17.195 s and 5.601 s respectively with its existing configuration. Both plans independently validated with zero violations. Python is 3.14.5 on Windows 11 with NetworkX 3.7; timing differences from the user's 14.7 s / 4.8 s are therefore not evidence of missing patch hunks and likely reflect runtime environment or benchmark conditions.
- Open: a definitive timing comparison requires the same machine, Python/dependency versions, configuration, and timer boundaries.
- Next: none.
- Commit/PR: pending

## 2026-10-16 — Route and display open passages as free space

- Status: done
- Changed: `cable_planner/solver/grid_router.py`, `cable_planner/visualization/renderer.py`, `tests/solver/test_grid_router.py`, `tests/validation/test_visualization.py`
- Changed: added evenly distributed route lanes every ~0.4 m along open passages, a soft 0.5 m preference between parallel cable runs, and a faint dashed blue passage indicator labelled as free space. The duplicate A*, permutation-pruning, and edge-index runtime hunks in the supplied patch were not reapplied; the active optimized code remains in place.
- Checked: five focused checks passed. Plans 14433 and 13033 independently validated with zero violations. With the new passage lanes and spacing preference, plan 14433 runs in 25.537 s at J=47.842788; plan 13033 runs in 7.019 s at J=32.092319. Compared with the preceding active solver, costs rose by 0.676 and 0.810 respectively, while route overlap and crossings remain zero. Refreshed plan-14433 overlay saved as `tmp/plan14433-open-passage.png`.
- Open: the added passage lanes enlarge the route graph and increase solve time despite the unchanged runtime optimization. The soft spacing preference trades a small amount of reported J for visually separated parallel runs.
- Next: review the new passage indication and decide whether the separation preference's current cost/runtime tradeoff is acceptable.
- Commit/PR: pending

## 2026-10-16 — Consolidate the working solver and demo into one package

- Status: complete
- Changed: `cable_planner/`, `tests/`, root project configuration, repository documentation
- Why: promote the verified 31.6972 plan-13033 grid router and checked Streamlit demo from temporary developer folders into a single maintained package
- Checked: direct package import selects `cable_planner.solver.grid_router.solve`; plan 13033 validates with zero crossings and route cost 31.6972; full suite passes (42 tests); Streamlit app check completes without errors and reports 31.6972; metre exporter returns the expected provisional format.
- Open: none for this integration pass.
- Next: changes are ready to fast-forward into `main`.
- Commit/PR: `d930234` integrates the package; merge from `origin/main` recorded in the following merge commit.
