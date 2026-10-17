# Cable Ring Planner

Normalize a trusted ResPlan floor plan, place the minimum feasible number of hubs, route one closed cable ring per hub, and independently verify the result. The solver minimizes hub count first, then `J = L + 5X + O + 0.5B`.

## React floor-plan demo

The React + FastAPI demo uses the trusted local `ResPlan.pkl` and `split.json`. The picker features **14433**, **13033**, and **14926** when they occur in the split, and searches every listed ID. Pressing **Run** normalizes and solves the selected plan again. Some raw plans have unusable geometry; the API reports diagnostics instead of inventing a solution. ResPlan data has development fallback nodes rather than organizer-supplied fixed nodes.

The input and independently checked output plans appear in large stacked views. A valid result also opens an interactive Three.js floor-plan viewer with assigned-room colors, schematic walls, windows, verified door and open-passage markers, every hub and node, and the solver's exact cable polylines. Select a hub to inspect its closed sequence, capacity, route length, and relevant diagnostics; select a node to see its room, hub, ring position, and coordinates. Drag to orbit, scroll to zoom, right-drag or use focused arrow keys to pan, or use **Top view** and **Reset camera**. Playback reveals the cable from hub through every assigned node and back to the same hub at an adjustable **simulated** speed. The 2D source has no wall elevations or door-leaf widths, so 3D wall height and opening width are visual conventions; floor, portal, node, hub, and cable positions retain their checked geometry.

From this repository root, install and start the API and frontend in separate terminals:

```powershell
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e .
npm --prefix frontend ci
.venv/Scripts/python.exe -m uvicorn cable_planner.web.app:app --reload --port 8001
```

```powershell
npm --prefix frontend run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to FastAPI on port 8001 by default; set `CABLE_RING_API_PROXY` to use another API address. The API also serves the production frontend at `http://localhost:8001` after `npm --prefix frontend run build`.

Local mode reads `archive/ResPlan.pkl` and `archive/split.json` in this checkout or its parent directory. Set `RESPLAN_ARCHIVE_PATH` and `RESPLAN_SPLIT_PATH` to other **trusted server-side files** if needed; the browser cannot upload a pickle or select arbitrary server paths. Featured plan thumbnails and the initial preview use the bundled plans so opening the page does not load the large local archive. The first lookup of another local plan loads the archive into a process cache; concurrent cold lookups share one load.

For a single-container build:

```powershell
docker build -t cable-ring-demo .
docker run --rm -p 8000:8000 -v "E:\dev\HackHive\archive:/app/archive:ro" cable-ring-demo
```

Open `http://localhost:8000`. The read-only archive mount is required for the local dataset picker.

The runtime panel reports server load, normalization, solve, validation, and render/export times for each run, plus total server time. Thumbnail generation, browser transfer, and 3D playback are outside the server timer. The viewer's estimated duration is its checked loop length divided by the selected simulated speed; it is not a solver prediction or a physical cable velocity. The objective panel uses the independent checker's `H`, `L`, `X`, `O`, `B`, `J`, and area gap; `best_known` does not claim global optimality.

After a run, download a complete PDF report with the input and checked-output images, checked metrics, diagnostics, timings, development JSON, provisional submission JSON, architecture data, and run metadata. The two standalone JSON downloads remain available: **Development Plan + Solution** follows `shared/schema/common.schema.json` in drawing units; **Slide 8 submission · provisional** follows the slide example in metres with a lower-left origin and is offered only when independent validation passes. The organizers have not published a complete machine-readable submission schema, so this export must be reviewed against any newer organizer contract before submission.

The React demo above is the local dataset workflow.

## Streamlit judge comparison

[Hosted Streamlit app](https://hackhive-cable-planner.streamlit.app/) (deployment of this branch pending). The Streamlit interface in `cable_planner/demo/app.py` runs checked-in example plans 12014, 8063, 4944, 8061, 13033, and 14433. Plans 12014 and 8063 are quick clean-ring examples. For penalized routes, it shows the best found independently checked zero-crossing or zero-overlap alternative when the bounded search finds one. Plan 4944 illustrates a lower-cost route with a crossing beside a higher-cost zero-crossing route; 8061 illustrates a search with no qualifying alternative found.

## Layout

| Path | Purpose |
| --- | --- |
| `cable_planner/ingestion/`, `cable_planner/geometry/` | Input normalization and traversability |
| `cable_planner/solver/` | Hub placement, connected assignment, and cable routing |
| `cable_planner/validation/`, `cable_planner/metrics/` | Independent rule checks and scoring |
| `cable_planner/visualization/`, `cable_planner/web/` | Checked 2D overlays, local API, and architectural 3D geometry |
| `shared/schema/` | Development Plan and Solution contract |
| `tests/` | Ingestion, solver, and validation tests |
| `examples/outputs/` | Checked sample plans and submission JSON |

## Run locally

To use your own `ResPlan.pkl`, run the app on the same computer (or server) that can read that file. A path entered in the hosted app refers to Streamlit's server, not to your computer, so the hosted app only offers the checked-in examples.

From the repository root, use the Windows Python launcher to create a virtual environment and install the project. This avoids accidentally using an MSYS2 `python` that may not include `pip`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m streamlit run cable_planner/demo/app.py
```

If `.venv` already exists but reports `No module named pip`, bootstrap pip in that environment and install the project:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -e .
```

If the dependencies are already installed, start the app directly:

```powershell
.\.venv\Scripts\python.exe -m streamlit run cable_planner/demo/app.py
```

In the app at `http://localhost:8501`:

1. Select **Trusted local ResPlan archive**.
2. Enter the full path to your archive, for example `E:\dev\HackHive\archive\ResPlan.pkl`.
3. Enter the plan ID and click **Run planner**.

The archive path defaults to `../archive/ResPlan.pkl` or `./archive/ResPlan.pkl` when either exists. Only load a pickle archive you trust because pickle files can execute code.

For a command-line run:

```powershell
.\.venv\Scripts\python.exe -m cable_planner.demo.end_to_end --plan-id 13033 --archive E:\dev\HackHive\archive\ResPlan.pkl --render overlay.png
```

Run the tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

Source code lives in `cable_planner`; the older developer-named folders have been consolidated into that package. The bundled archive does not contain organizer-provided fixed node points, so its generated nodes are deterministic development fallbacks.
