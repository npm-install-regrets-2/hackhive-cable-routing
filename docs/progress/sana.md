# Sana's progress

Append entries using the format in `docs/README.md`. Owns independent validation, metrics, visualization, and the end-to-end demo.

## 2026-10-16 — Side-by-side normalized input and checked output

- Status: done
- Changed: `sana/visualization/renderer.py`, `sana/visualization/__init__.py`, `sana/demo/app.py`, root runtime files, and provisional export support
- Why: make manual pipeline inspection compare normalized source geometry directly with solver assignments and independently checked routes
- Checked: `python -m py_compile sana/demo/app.py sana/visualization/renderer.py sana/export/metres.py sana/export/__init__.py` passed; `git diff --check` passed
- Open: import/render smoke testing and browser execution could not run because the available local Python environments lack the required packages, and Docker is not installed
- Next: install the root requirements in a local environment and launch the documented demo
- Commit/PR: pending

## 2026-10-15 — Initial independent validator, checker metrics, visual renderer, and canonical fixtures

- Status: done
- Changed: `shared/fixtures/*`, `sana/validation/*`, `sana/metrics/*`, `sana/visualization/*`, `sana/demo/*`, `sana/tests/*`
- Why: establish independent hard-rule validation and recomputed metrics without trusting solver claims, provide hand-checked canonical fixtures to Harshit and Priyanshu, and build visual overlays matching checked data
- Checked: `python -m pytest sana/tests -v` (17 tests passing across schema validity, exact metrics, validator hard rules, and visual rendering); `python -m sana.demo.runner --combined shared/fixtures/canonical_combined.json` executed successfully
- Open: awaiting Harshit's normalized plan loader and Priyanshu's optimizer output for live end-to-end integration
- Next: connect Harshit's loader and Priyanshu's solver into the interactive demo interface once their initial PRs land
- Commit/PR: branch `task/sana-validation-metrics`
