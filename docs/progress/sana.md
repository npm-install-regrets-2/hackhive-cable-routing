# Sana's progress

Append entries using the format in `docs/README.md`. Owns independent validation, metrics, visualization, and the end-to-end demo.

## 2026-10-17 — Keep comparison image frames aligned with their cards

- Status: done
- Changed: `frontend/src/style.css`
- Why: the two image cards share a grid row whose height follows the taller floor-plan image, but each inner frame previously stopped at its own content height and exposed the card background as a mismatched band
- Checked: `npm run build` in `frontend/` passed; Vite reported the existing large-chunk advisory
- Open: none
- Next: visually inspect the comparison at desktop and narrow widths when the UI is running
- Commit/PR: pending

## 2026-10-15 — Initial independent validator, checker metrics, visual renderer, and canonical fixtures

- Status: done
- Changed: `shared/fixtures/*`, `sana/validation/*`, `sana/metrics/*`, `sana/visualization/*`, `sana/demo/*`, `sana/tests/*`
- Why: establish independent hard-rule validation and recomputed metrics without trusting solver claims, provide hand-checked canonical fixtures to Harshit and Priyanshu, and build visual overlays matching checked data
- Checked: `python -m pytest sana/tests -v` (17 tests passing across schema validity, exact metrics, validator hard rules, and visual rendering); `python -m sana.demo.runner --combined shared/fixtures/canonical_combined.json` executed successfully
- Open: awaiting Harshit's normalized plan loader and Priyanshu's optimizer output for live end-to-end integration
- Next: connect Harshit's loader and Priyanshu's solver into the interactive demo interface once their initial PRs land
- Commit/PR: pull request #2 (merged into `main`)

## 2026-10-15 — 3-way end-to-end integration and pipeline demo

- Status: done
- Changed: `sana/demo/end_to_end.py`, `sana/tests/test_end_to_end.py`, `docs/progress/sana.md`
- Why: integrate Harshit's normalization (PR #3) and Priyanshu's thin solver (PR #1) with Sana's independent validation and visualizer into a complete end-to-end pipeline
- Checked: `python sana/demo/end_to_end.py --sample-raw` runs raw ResPlan normalization, solves ring, independently validates solution, recomputes metrics, and renders overlay; `python -m pytest sana/tests -v` (18 tests passing)
- Open: obstacle-aware grid routing in Priyanshu's solver and raw archive loading for larger ResPlan benchmark
- Next: build the Streamlit interactive dashboard linking this pipeline
- Commit/PR: pending

## 2026-10-16 — Side-by-side normalized input and checked output

- Status: done
- Changed: `sana/visualization/renderer.py`, `sana/visualization/__init__.py`, `sana/demo/app.py`, root runtime files, and provisional export support
- Why: make manual pipeline inspection compare normalized source geometry directly with solver assignments and independently checked routes
- Checked: `python -m py_compile sana/demo/app.py sana/visualization/renderer.py sana/export/metres.py sana/export/__init__.py` passed; `git diff --check` passed
- Open: import/render smoke testing and browser execution could not run because the available local Python environments lack the required packages, and Docker is not installed
- Next: install the root requirements in a local environment and launch the documented demo
- Commit/PR: pending

## 2026-10-16 — Kaggle dataset integration, official Slide 8 submission format, and placement scenario tests

- Status: done
- Changed: `sana/export.py`, `sana/demo/end_to_end.py`, `sana/tests/test_export.py`, `sana/tests/test_hub_placement_scenarios.py`, `.gitignore`
- Why: access the 17,000-plan ResPlan archive, test plans from the dataset directly, implement the official Slide 8 submission JSON format in physical metres, and add 5 stress scenarios verifying hub placement legality and capacity constraints
- Checked: `python -m pytest sana/tests -v` (all 24 tests passing); `python sana/demo/end_to_end.py --plan-id 14926` executed on real dataset plan; official Slide 8 JSON export validated
- Open: obstacle-aware grid pathfinding in Priyanshu's solver
- Next: wrap the full pipeline into the Streamlit presentation app
- Commit/PR: pending

## 2026-10-16 — Repair Streamlit demo and show live checked route cost

- Status: done
- Changed: `sana/demo/app.py`, `sana/visualization/renderer.py`, `sana/tests/test_streamlit_app.py`
- Why: the app imported a nonexistent trusted-archive module and input renderer, and a long-running Streamlit process could keep an older solver module in memory
- Checked: Streamlit AppTest starts without exceptions; plan 13033 run shows checked route cost 31.6972 and renders both figures; local Streamlit server health check passes on port 8502
- Open: none for the demo; solver quality remains Priyanshu's workstream
- Next: use the running app to inspect additional plan IDs and compare checked metrics
- Commit/PR: pending
