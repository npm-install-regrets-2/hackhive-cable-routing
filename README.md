# Cable Ring Planner

Normalize a trusted ResPlan floor plan, place the minimum feasible number of hubs, route one closed cable ring per hub, and independently verify the result. The solver minimizes hub count first, then `J = L + 5X + O + 0.5B`.

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

Install the project in an environment with Python 3.11 or newer:

```powershell
python -m pip install -e .
python -m streamlit run cable_planner/demo/app.py
```

Open `http://localhost:8501`, enter a plan ID, and click **Run planner**. The app defaults to plan 13033 and shows the independently checked cost and input/output floor plans. It looks for `ResPlan.pkl` in either `../archive/` or `./archive/`; the archive path can also be entered in the app. Only use the locally trusted archive because Python pickle can execute code.

For a command-line run:

```powershell
python -m cable_planner.demo.end_to_end --plan-id 13033 --archive E:\dev\HackHive\archive\ResPlan.pkl --render overlay.png
```

Run the tests with `python -m pytest tests`. Source code lives in `cable_planner`; the older developer-named folders have been consolidated into that package. The bundled archive does not contain organizer-provided fixed node points, so its generated nodes are deterministic development fallbacks.
