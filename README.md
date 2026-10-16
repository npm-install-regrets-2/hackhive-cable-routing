# Cable Ring Planner

Normalize a trusted ResPlan floor plan, place the minimum feasible number of hubs, route one closed cable ring per hub, and independently verify the result. The solver minimizes hub count first, then `J = L + 5X + O + 0.5B`.

[Launch the Streamlit app](https://hackhive-cable-planner.streamlit.app/)

The hosted app can run the checked-in example plans 13033 and 14433. Local runs can also use a trusted ResPlan archive.

## Layout

| Path | Purpose |
| --- | --- |
| `cable_planner/ingestion/`, `cable_planner/geometry/` | Input normalization and traversability |
| `cable_planner/solver/` | Hub placement, connected assignment, and cable routing |
| `cable_planner/validation/`, `cable_planner/metrics/` | Independent rule checks and scoring |
| `cable_planner/visualization/`, `cable_planner/demo/` | Checked overlays and the Streamlit app |
| `shared/schema/` | Development Plan and Solution contract |
| `tests/` | Ingestion, solver, and validation tests |
| `examples/outputs/` | Checked sample plans and submission JSON |

## Run locally

To use your own `ResPlan.pkl`, run the app on the same computer (or server) that can read that file. A path entered in the hosted app refers to Streamlit's server, not to your computer, so the hosted app only offers the checked-in examples.

From the repository root, install the project in an environment with Python 3.11 or newer and start Streamlit:

```powershell
python -m pip install -e .
python -m streamlit run cable_planner/demo/app.py
```

In the app at `http://localhost:8501`:

1. Select **Trusted local ResPlan archive**.
2. Enter the full path to your archive, for example `E:\dev\HackHive\archive\ResPlan.pkl`.
3. Enter the plan ID and click **Run planner**.

The archive path defaults to `../archive/ResPlan.pkl` or `./archive/ResPlan.pkl` when either exists. Only load a pickle archive you trust because pickle files can execute code.

For a command-line run:

```powershell
python -m cable_planner.demo.end_to_end --plan-id 13033 --archive E:\dev\HackHive\archive\ResPlan.pkl --render overlay.png
```

Run the tests with `python -m pytest tests`. Source code lives in `cable_planner`; the older developer-named folders have been consolidated into that package. The bundled archive does not contain organizer-provided fixed node points, so its generated nodes are deterministic development fallbacks.
