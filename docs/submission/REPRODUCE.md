# Reproduce the PS4 demo

This package was generated from the [`feat/judge-route-comparison-current` branch](https://github.com/npm-install-regrets-2/hackhive-cable-routing/tree/feat/judge-route-comparison-current) of [the Cable Ring Planner repository](https://github.com/npm-install-regrets-2/hackhive-cable-routing). [Review PR #7](https://github.com/npm-install-regrets-2/hackhive-cable-routing/pull/7) contains the judge-comparison features and this report package. Use that branch until it is reviewed and merged.

1. From the repository root, install Python 3.11+ dependencies with `uv venv .venv` and `uv pip install --python .venv/Scripts/python.exe -e .`.
2. Install the frontend with `npm --prefix frontend ci`.
3. In one terminal start `.venv/Scripts/python.exe -m uvicorn cable_planner.web.app:app --reload --port 8001`; in another run `npm --prefix frontend run dev`.
4. Open `http://localhost:5173`, select bundled plan **4944**, and click **Run**. Inspect the source plan, selected ring, independently checked zero-crossing alternative, and metrics. Plan **12014** and **8063** are saved clean examples in the package even if they are not featured in the Vite selector.
5. To browse another raw plan, extract this ZIP into the repository root (or its parent directory) with Python 3.11+: `python -m zipfile -e npminstallregrets_PS4.zip <repository-root>`. The large pickle uses ZIP's LZMA method, which some built-in ZIP viewers do not support. The local API reads the included `archive/ResPlan.pkl` and `archive/split.json`; the browser does not upload pickle files. Only open pickles from sources you trust. Plan **16416** requires this local archive.

The package's `examples/` folder contains checked development Plan + Solution documents in drawing units. `shared/schema/common.schema.json` is the development interchange contract. The provisional organizer-style export uses metres and a different shape. Do not relabel a development JSON as an official organizer submission.

Run backend tests with `.venv/Scripts/python.exe -m pytest tests` and frontend tests with `npm --prefix frontend test`. The package builder in the repo is `.venv/Scripts/python.exe docs/submission/build_package.py`; it validates included JSON, reruns the 4944 comparison, renders the checked figures, builds the PDF, and refreshes `submission/npminstallregrets_PS4.zip`.
