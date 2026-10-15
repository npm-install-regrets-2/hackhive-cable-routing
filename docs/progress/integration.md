# Integration progress

## 2026-10-16 — Consolidate the working solver and demo into one package

- Status: complete
- Changed: `cable_planner/`, `tests/`, root project configuration, repository documentation
- Why: promote the verified 31.6972 plan-13033 grid router and checked Streamlit demo from temporary developer folders into a single maintained package
- Checked: direct package import selects `cable_planner.solver.grid_router.solve`; plan 13033 validates with zero crossings and route cost 31.6972; full suite passes (42 tests); Streamlit app check completes without errors and reports 31.6972; metre exporter returns the expected provisional format.
- Open: none for this integration pass.
- Next: changes are ready to fast-forward into `main`.
- Commit/PR: `d930234` integrates the package; merge from `origin/main` recorded in the following merge commit.
